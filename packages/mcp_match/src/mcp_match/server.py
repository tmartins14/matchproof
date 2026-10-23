"""The match-data MCP server: the agents' only door to a match (ADR 0008).

`build_server(store, writable)` defines every read tool once; `put_claims` is added only when
`writable` is true. The public server is read-only and mounted over HTTP; the internal one is used
in process by the agent workflow and is never exposed. No tool computes a statistic: facts come from
the registry and everything else is stored data, rounded or filtered but not derived.
"""

import os
from typing import Any

from contracts.models import Audit, Claim, Event, Fact, PositionFrame
from intel.beats import swing_fact_ids
from intel.labels import LabelContext, label_for
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel, ValidationError

from .store import MatchStore, UnknownMatch

HTTP_PATH = "/mcp"  # where the HTTP app serves the server
LOCAL_HOSTS = ("localhost:*", "127.0.0.1:*")
MAX_FACTS = 200  # most facts one find_facts call returns
MAX_EVENTS = 200  # most events one get_events call returns
FREEZE_FRAME_DECIMALS = 1  # positions are rounded to 0.1 m
NEEDS_REASON = frozenset({"rephrased", "blocked"})
NEEDS_FACTS = frozenset({"verified", "rephrased"})

INSTRUCTIONS = (
    "Facts, events, freeze frames and beats of a synthetic football match, read from the match "
    "store. Every number comes from a fact. Times are match seconds. Pitch positions are metres "
    "on a 120 by 80 pitch, and the home team attacks toward x = 120. A match that is still "
    "streaming shows only what has been computed so far."
)


def transport_security_from_env() -> TransportSecuritySettings:
    """DNS-rebinding protection on, for localhost and the comma-separated host names in
    MCP_ALLOWED_HOSTS (the deployed app's own host name; infra/ sets it)."""
    extra = [
        h.strip()
        for h in os.environ.get("MCP_ALLOWED_HOSTS", "").split(",")
        if h.strip()
    ]
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[*LOCAL_HOSTS, *extra],
        allowed_origins=[f"http://{h}" for h in LOCAL_HOSTS]
        + [f"https://{h}" for h in extra],
    )


def dump(model: BaseModel) -> dict[str, Any]:
    out: dict[str, Any] = model.model_dump(
        mode="json", by_alias=True, exclude_none=True
    )
    return out


def clamp_limit(limit: int, ceiling: int) -> int:
    if limit < 1:
        raise ToolError("limit must be at least 1.")
    return min(limit, ceiling)


def rounded_freeze_frame(frame: PositionFrame) -> dict[str, Any]:
    """The frame as stored, minus per-tick fields, with positions rounded to 0.1 m."""

    def point(p: Any) -> list[float]:
        return [round(float(v), FREEZE_FRAME_DECIMALS) for v in p]

    raw = dump(frame)
    raw["ball"] = point(raw["ball"])
    raw["players"] = [
        {"id": p["id"], "side": p["side"], "at": point(p["at"])} for p in raw["players"]
    ]
    return raw


def fact_in_range(fact: Fact, t_from: float | None, t_to: float | None) -> bool:
    """A fact is in range when its time scope overlaps it; facts with no time scope are not."""
    if t_from is None and t_to is None:
        return True
    scope = fact.scope
    if scope is None or scope.t_from is None or scope.t_to is None:
        return False
    if t_from is not None and scope.t_to.root < t_from:
        return False
    return not (t_to is not None and scope.t_from.root > t_to)


def visible_facts(store: MatchStore, match_id: str, upto: float | None) -> list[Fact]:
    """Facts a viewer may see at playback position `upto` (None: all). A fact is visible when its
    time scope ends by then, or when a visible beat cites it. Facts with no time scope wait for
    the end of the match."""
    facts = store.registry(match_id).all()
    if upto is None:
        return facts
    cited = {
        f.root
        for b in store.beats(match_id)
        if b.t_detect.root <= upto
        for f in b.fact_ids
    }
    return [
        f
        for f in facts
        if f.id.root in cited
        or (
            f.scope is not None
            and f.scope.t_to is not None
            and f.scope.t_to.root <= upto
        )
    ]


def claim_errors(
    store: MatchStore, match_id: str, beat_id: str, raw: Any, seen: set[str]
) -> tuple[Claim | None, list[str]]:
    """The claim, if it is acceptable, and every reason it is not."""
    try:
        claim = Claim.model_validate(raw)
    except ValidationError as exc:
        return None, [
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}"
            for e in exc.errors(
                include_url=False, include_context=False, include_input=False
            )
        ]
    errors: list[str] = []
    verdict = claim.verdict.value
    if claim.beat_id.root != beat_id:
        errors.append(f"beat_id is {claim.beat_id.root}, not {beat_id}.")
    if verdict in NEEDS_REASON and (claim.reason is None or claim.draft_text is None):
        errors.append(f"A {verdict} claim needs reason and draft_text.")
    if verdict in NEEDS_FACTS and not claim.fact_ids:
        errors.append(f"A {verdict} claim needs at least one fact id.")
    registry = store.registry(match_id)
    cited = [f.root for f in claim.fact_ids] + [n.fact_id.root for n in claim.numbers]
    for fid in dict.fromkeys(cited):
        try:
            registry.get(fid)
        except KeyError:
            errors.append(f"Unknown fact id {fid}.")
    existing = {c.id.root for cs in store.claims(match_id).values() for c in cs}
    if claim.id.root in existing or claim.id.root in seen:
        errors.append(f"Claim id {claim.id.root} is already used.")
    return (claim if not errors else None), errors


def build_server(store: MatchStore, writable: bool) -> FastMCP:
    """The match-data server over `store`. Only a writable server has `put_claims`.

    A read-only server is the public one: while a match is streaming it shows only what viewers
    have already seen (events, facts and beats at or before the playback position). The writable
    server is internal and sees the full lookahead."""
    server = FastMCP(
        "match-data",
        instructions=INSTRUCTIONS,
        streamable_http_path=HTTP_PATH,
        stateless_http=True,
        json_response=True,
        transport_security=transport_security_from_env(),
    )

    def known_match(match_id: str) -> None:
        try:
            store.brief(match_id)
        except UnknownMatch as exc:
            raise ToolError(f"Unknown match {match_id}.") from exc

    def horizon(match_id: str) -> float | None:
        """Latest match time this server may show; None means no limit."""
        return None if writable else store.playback(match_id)

    def known_fact(match_id: str, fact_id: str) -> Fact:
        known_match(match_id)
        unknown = ToolError(f"Unknown fact {fact_id} in match {match_id}.")
        try:
            fact = store.registry(match_id).get(fact_id)
        except KeyError as exc:
            raise unknown from exc
        if horizon(match_id) is not None and fact_id not in {
            f.id.root for f in visible_facts(store, match_id, horizon(match_id))
        }:
            raise unknown
        return fact

    @server.tool()
    def get_brief(match_id: str) -> dict[str, Any]:
        """The match brief: teams, tactics, storyline and seed."""
        known_match(match_id)
        return dump(store.brief(match_id))

    @server.tool()
    def get_fact(match_id: str, fact_id: str) -> dict[str, Any]:
        """One fact in full: value, unit, display renderings, scope and source ids."""
        return dump(known_fact(match_id, fact_id))

    @server.tool()
    def find_facts(
        match_id: str,
        name_prefix: str | None = None,
        side: str | None = None,
        t_from: float | None = None,
        t_to: float | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Facts, in id order. Filter by name prefix (for example "field_tilt"), side (home or
        away), and a time range in match seconds that the fact's own time scope overlaps. At most
        200 are returned; `total` is how many matched."""
        known_match(match_id)
        if side is not None and side not in ("home", "away"):
            raise ToolError("side must be home or away.")
        facts = [
            f
            for f in visible_facts(store, match_id, horizon(match_id))
            if (name_prefix is None or f.name.startswith(name_prefix))
            and (
                side is None
                or (
                    f.scope is not None
                    and f.scope.side is not None
                    and f.scope.side.value == side
                )
            )
            and fact_in_range(f, t_from, t_to)
        ]
        cap = clamp_limit(limit, MAX_FACTS)
        return {"facts": [dump(f) for f in facts[:cap]], "total": len(facts)}

    @server.tool()
    def get_events(
        match_id: str,
        t_from: float,
        t_to: float,
        types: list[str] | None = None,
        limit: int = 200,
    ) -> dict[str, Any]:
        """Events between two match times, oldest first, optionally only some types (for example
        shot or card). At most 200 are returned; `total` is how many matched."""
        known_match(match_id)
        wanted = set(types) if types else None
        upto = horizon(match_id)
        events: list[Event] = [
            e
            for e in store.events(match_id)
            if t_from <= e.t.root <= t_to
            and (upto is None or e.t.root <= upto)
            and (wanted is None or e.type.value in wanted)
        ]
        cap = clamp_limit(limit, MAX_EVENTS)
        return {"events": [dump(e) for e in events[:cap]], "total": len(events)}

    @server.tool()
    def get_freeze_frame(match_id: str, event_id: str) -> dict[str, Any]:
        """The 22 players and the ball at one event: ids, sides and positions rounded to 0.1 m."""
        known_match(match_id)
        frame = store.freeze_frame(match_id, event_id)
        upto = horizon(match_id)
        if frame is not None and upto is not None and frame.t.root > upto:
            frame = None
        if frame is None:
            raise ToolError(
                f"No freeze frame for event {event_id} in match {match_id}."
            )
        return rounded_freeze_frame(frame)

    @server.tool()
    def list_beats(match_id: str, after_t: float | None = None) -> dict[str, Any]:
        """The beats found so far, in the order they were detected. Pass `after_t` to get only
        beats detected after that match time."""
        known_match(match_id)
        upto = horizon(match_id)
        beats = [
            b
            for b in store.beats(match_id)
            if (after_t is None or b.t_detect.root > after_t)
            and (upto is None or b.t_detect.root <= upto)
        ]
        return {"beats": [dump(b) for b in beats]}

    @server.tool()
    def get_beat_bundle(match_id: str, beat_id: str) -> dict[str, Any]:
        """One beat and every fact it cites, in one call, each with a plain-English `label`. This is
        what the Narrator reads."""
        known_match(match_id)
        upto = horizon(match_id)
        beat = next(
            (
                b
                for b in store.beats(match_id)
                if b.id.root == beat_id and (upto is None or b.t_detect.root <= upto)
            ),
            None,
        )
        if beat is None:
            raise ToolError(f"Unknown beat {beat_id} in match {match_id}.")
        facts = [known_fact(match_id, f.root) for f in beat.fact_ids]
        if beat.kind.value == "momentum_swing":
            # Only the changes big enough to be the story; a 1 m\u00b2 drift is not narrated.
            keep = swing_fact_ids(facts)
            facts = [f for f in facts if f.id.root in keep] or facts
        if beat.kind.value == "card":
            # The card, who, when and how many are left. The foul's freeze-frame counts are not the
            # story, and the Narrator turned them into "defenders in the box at the set piece".
            facts = [f for f in facts if f.name.startswith("card(")] or facts
        brief = store.brief(match_id)
        ctx = LabelContext(
            {"home": brief.home.name, "away": brief.away.name},
            {e.id.root: e for e in store.events(match_id)},
            store.registry(match_id),
        )
        # `label` is not part of the Fact schema: it is added here, by code, for the Narrator.
        return {
            "beat": dump(beat),
            "facts": [{**dump(f), "label": label_for(f, ctx)} for f in facts],
        }

    if writable:

        @server.tool()
        def put_claims(
            match_id: str, beat_id: str, claims: list[dict[str, Any]]
        ) -> dict[str, Any]:
            """Store claims for a beat. Each claim must match the claim schema, belong to the beat
            and cite only known fact ids. Valid claims are stored even if others are rejected;
            `results` says which, with the errors for each."""
            known_match(match_id)
            if not any(b.id.root == beat_id for b in store.beats(match_id)):
                raise ToolError(f"Unknown beat {beat_id} in match {match_id}.")
            accepted: list[Claim] = []
            seen: set[str] = set()
            results: list[dict[str, Any]] = []
            for i, raw in enumerate(claims):
                claim, errors = claim_errors(store, match_id, beat_id, raw, seen)
                claim_id = raw.get("id") if isinstance(raw, dict) else None
                if claim is not None:
                    accepted.append(claim)
                    seen.add(claim.id.root)
                results.append(
                    {
                        "index": i,
                        "claim_id": claim_id,
                        "accepted": claim is not None,
                        "errors": errors,
                    }
                )
            if accepted:
                store.put_claims(match_id, beat_id, accepted)
            return {"results": results}

        @server.tool()
        def put_audit(
            match_id: str, claim_id: str, audit: dict[str, Any]
        ) -> dict[str, Any]:
            """Attach the independent auditor's result to a stored claim. It never changes the
            claim's verdict."""
            known_match(match_id)
            try:
                parsed = Audit.model_validate(audit)
            except ValidationError as exc:
                raise ToolError(f"Invalid audit: {exc.error_count()} errors.") from exc
            if not store.put_audit(match_id, claim_id, parsed):
                raise ToolError(f"Unknown claim {claim_id} in match {match_id}.")
            return {"claim_id": claim_id, "stored": True}

    return server
