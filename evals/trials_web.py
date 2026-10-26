"""Narrator Trials results to the file the web pages draw. No model calls.

The browser draws JSON and never computes (seam rule 3), so ranks, worst moments, picks, clocks and
the facts behind each moment are all worked out here. Each fixture's match is rebuilt from the pack
(generation is deterministic and cached), never re-played.

uv run python -m evals.trials_web evals/reports/trials/pack-v1.json    # writes web-pack-v1.json
"""

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml
from agents.llm_client import load_models
from agents.pipeline import tool_result
from agents.reconcile import (
    NO_FACTS_REASON,
    NOT_IN_BUNDLE_REASON,
    NUMBER_REASON_PREFIX,
    PLAYER_REASON_PREFIX,
    reconcile,
)
from contracts.models import Beat, Event, Fact, TrialsWeb
from intel.display import render_minute
from mcp_match import InMemoryMatchStore, build_server

from .golden import build_store_from_brief
from .run import ROOT
from .trials import PACK_PATH, POINTS, UNKNOWN_FACT_PREFIX, Fixture, load_pack

NEXT_UP_PATH = Path(__file__).parent / "trials" / "next_up.yaml"
WEB_FIXTURES_DIR = ROOT / "apps" / "web" / "fixtures" / "trials"
MAX_HELD_SHARE = (
    0.10  # a candidate with more beats unanswered than this is not measured
)
NOTE_CHARS = 90
CODE_BUCKETS = ("numbers", "names", "citation")  # caught in code, before any judge
MAX_SOURCES = 6
SIZE_LIMIT = 1_500_000
# Lowest first: what the worst moment is picked from.
VERDICT_ORDER = {"OVERTURNED": 0, "AMENDED": 1, "HELD": 2, "STANDS": 3}
REVIEWER_PREFIX = re.compile(r"^(?:Judge|Second reviewer) \([^)]*\):\s*")

Json = dict[str, Any]


def is_measured(row: Json) -> bool:
    """held / claims <= 0.10. A run the model mostly did not answer is not a result."""
    return bool(row["claims"] > 0 and row["held"] / row["claims"] <= MAX_HELD_SHARE)


def ranks_of(summary: list[Json]) -> tuple[Json, list[str]]:
    """1-based ranks of the measured rows in summary order, and the Table order: measured rows by
    rank, then the unmeasured ones (no rank)."""
    measured = [r["candidate"] for r in summary if is_measured(r)]
    unmeasured = [r["candidate"] for r in summary if not is_measured(r)]
    return {c: i for i, c in enumerate(measured, 1)}, [*measured, *unmeasured]


def trim(text: str, limit: int = NOTE_CHARS) -> str:
    """Cut at a word boundary to about `limit` characters, with an ellipsis."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    space = cut.rfind(" ")
    if space > limit // 2:
        cut = cut[:space]
    return cut.rstrip(" ,;:.-") + "…"


def citation_words(reason: str) -> str | None:
    """A citation reason in plain English, with no fact id in it; None for any other reason."""
    if reason.startswith(UNKNOWN_FACT_PREFIX):
        return "cited a fact that doesn't exist"
    if reason.endswith(NOT_IN_BUNDLE_REASON):
        return "cited a fact it wasn't given"
    if reason == NO_FACTS_REASON:
        return "cited no facts"
    return None


def reason_for(bucket: str | None, reasons: list[str]) -> str:
    """The first reason that belongs to the bucket, else the first reason."""
    if bucket == "numbers":
        match = next((r for r in reasons if r.startswith(NUMBER_REASON_PREFIX)), None)
    elif bucket == "names":
        match = next((r for r in reasons if r.startswith(PLAYER_REASON_PREFIX)), None)
    elif bucket == "citation":
        match = next((r for r in reasons if citation_words(r)), None)
    else:
        match = None
    return match or reasons[0]


def note_of(claim: Json) -> str:
    """`<bucket>: <reason>` with the reviewer's prefix ("Judge (overclaim): ") stripped. The reason
    is the one that matches the bucket; citation reasons are plain English, never a fact id."""
    reasons = claim["reasons"]
    if not reasons:
        return trim(claim["text"])
    bucket = claim["reason_bucket"]
    reason = reason_for(bucket, reasons)
    reason = citation_words(reason) or REVIEWER_PREFIX.sub("", reason)
    return trim(f"{bucket}: {reason}" if bucket else reason)


def worst_of(
    claims: list[Json], candidate: str, traps: frozenset[tuple[str, str]] = frozenset()
) -> Json | None:
    """The candidate's worst scored claim. Trap-beat claims come first: if any of them is not STANDS,
    the pick is from those, else from every scored claim. Lowest verdict first (OVERTURNED < AMENDED <
    HELD < STANDS); on a tie, a claim code caught (numbers, names, citation) before a judge-caught
    one; then the latest beat."""
    rows = [c for c in claims if c["candidate"] == candidate and c["scored"]]
    if not rows:
        return None
    on_trap = [c for c in rows if (c["fixture"], c["beat"]) in traps]
    pool = on_trap if any(c["verdict"] != "STANDS" for c in on_trap) else rows
    low = min(VERDICT_ORDER[c["verdict"]] for c in pool)
    lowest = [c for c in pool if VERDICT_ORDER[c["verdict"]] == low]
    coded = [c for c in lowest if c["reason_bucket"] in CODE_BUCKETS]
    pick = max(coded or lowest, key=lambda c: (c["minute"], c["beat"]))
    return {
        "fixture": pick["fixture"],
        "beat": pick["beat"],
        "verdict": pick["verdict"],
        "note": note_of(pick),
    }


def trap_record_of(
    claims: list[Json], candidate: str, traps: frozenset[tuple[str, str]]
) -> Json:
    """Counts of each verdict over the candidate's scored claims on trap beats."""
    record = dict.fromkeys(VERDICT_ORDER, 0)
    for c in claims:
        if (
            c["candidate"] == candidate
            and c["scored"]
            and (c["fixture"], c["beat"]) in traps
        ):
            record[c["verdict"]] += 1
    return record


def fail_top_of(profile: Json) -> Json | None:
    """The biggest bucket of the fail profile, or null when nothing failed."""
    if not profile:
        return None
    bucket = max(profile, key=lambda b: profile[b])
    return {"bucket": bucket, "share": profile[bucket]}


def picks_of(summary: list[Json]) -> Json:
    """The cards under the table, from measured rows only. Each is null when nothing qualifies."""
    measured = [r for r in summary if is_measured(r)]
    cleared = [r for r in measured if r["cleared"]]
    priced = [r for r in cleared if not isinstance(r["usd_per_match"], str)]
    live = min(cleared, key=lambda r: r["p90_ms"], default=None)
    budget = min(priced, key=lambda r: r["usd_per_match"], default=None)
    uncleared = [r["candidate"] for r in measured if not r["cleared"]]
    return {
        "live_feed": (
            {"candidate": live["candidate"], "p90_ms": live["p90_ms"]} if live else None
        ),
        "budget": (
            {"candidate": budget["candidate"], "usd_per_match": budget["usd_per_match"]}
            if budget
            else None
        ),
        "not_cleared": uncleared or None,
        "sole": (
            {
                "candidate": cleared[0]["candidate"],
                "p90_ms": cleared[0]["p90_ms"],
                "usd_per_match": (
                    None
                    if isinstance(cleared[0]["usd_per_match"], str)
                    else cleared[0]["usd_per_match"]
                ),
            }
            if len(cleared) == 1
            else None
        ),
    }


def live_narrator_of(candidates: list[Json], deployment: str) -> str | None:
    """The candidate whose deployment is the one the API narrates with live."""
    return next((c["id"] for c in candidates if c["deployment"] == deployment), None)


def clock_at(events: list[Event], t: float) -> str:
    """The broadcast clock at match time `t`, with the period of the last event at or before it."""
    before = [e for e in events if e.t.root <= t]
    period = int((before[-1] if before else events[0]).period.value)
    return render_minute(t, "en", period)[0]


# What each trap kind is called on the Fixtures page and the Desk, before the broadcast clock.
TRAP_NAMES = {
    "red_card": "RED CARD",
    "penalty": "PENALTY",
    "open_play_goal": "GOAL",
    "set_piece_goal": "SET-PIECE GOAL",
    "counter_goal": "COUNTER GOAL",
    "high_turnover_goal": "TURNOVER GOAL",
}


def trap_label(kind: str, note: str, clock: str) -> str:
    """The chip text of a trap, such as `RED CARD 61′` or `STOPPAGE-TIME PENALTY 90+8′`.

    The kind names it; the note says when the moment is more than that (a winner, an equaliser); a
    clock in stoppage time makes a penalty a stoppage-time penalty.
    """
    low = note.lower()
    name = TRAP_NAMES[kind]
    if kind != "red_card" and ("winner" in low or "lead changes hands" in low):
        name = "LATE WINNER"
    elif kind != "red_card" and ("equaliser" in low or " level" in low):
        name = "EQUALISER"
    elif kind == "penalty" and "+" in clock:
        name = "STOPPAGE-TIME PENALTY"
    return f"{name} {clock}"


def labelled_traps(traps: list[Json], events: list[Event]) -> list[Json]:
    """Each trap with its `label`, the clock read at the trap's own event."""
    by_id = {e.id.root: e for e in events}
    return [
        {
            **t,
            "label": trap_label(
                t["kind"], t["note"], clock_at(events, by_id[t["event_id"]].t.root)
            ),
        }
        for t in traps
    ]


def trap_beats(fixture: Fixture, beats: list[Beat]) -> list[Json]:
    """The beat each trap sits on: the planted beat, whose anchor is the trap's event."""
    by_planted = {b.planted_beat_id: b for b in beats if b.planted_beat_id}
    rows = []
    for trap in fixture.traps:
        beat = by_planted[f"pb-{int(trap['planted']):02d}"]
        rows.append({"beat": beat.id.root, "event_id": beat.anchor_event_id.root})
    return rows


async def bundles_of(
    store: InMemoryMatchStore, match_id: str, beat_ids: list[str]
) -> dict[str, Json]:
    """The bundle the Narrator read for each beat, through the same tool."""
    server = build_server(store, writable=False)
    return {
        beat_id: tool_result(
            await server.call_tool(
                "get_beat_bundle", {"match_id": match_id, "beat_id": beat_id}
            )
        )
        for beat_id in beat_ids
    }


def aired_text(claim: Json) -> str:
    """The wording the Desk's claim carries: a blocked claim keeps the Narrator's draft for audit."""
    blocked = claim["verdict"] in ("OVERTURNED", "HELD")
    return str(
        claim["draft_text"] if blocked and claim["draft_text"] else claim["text"]
    )


def numbers_of(claim: Json, bundle: Json) -> list[Json]:
    """Each number in the claim's wording tied to the cited fact it matches: the deterministic
    reconciler run on the row, no model. Facts it cites that are not in the bundle match nothing."""
    facts = {f["id"]: Fact.model_validate(f) for f in bundle["facts"]}
    found = reconcile(aired_text(claim), claim["fact_ids"], facts)
    return [{"as_written": n.as_written, "fact_id": n.fact_id} for n in found.numbers]


def moment_of(
    store: InMemoryMatchStore,
    match_id: str,
    beat: Beat,
    bundle: Json,
    events: list[Event],
) -> Json:
    """One beat as the Compare page draws it."""
    brief = store.brief(match_id)
    roster = {p.id.root: p.name for t in (brief.home, brief.away) for p in t.players}
    by_id = {e.id.root: e for e in events}
    anchor = beat.anchor_event_id.root
    ids = [anchor] if anchor in by_id else []
    for fact in bundle["facts"]:
        for s in fact["source_ids"]:
            if s in by_id and s not in ids:
                ids.append(s)
    sources = []
    for eid in ids[:MAX_SOURCES]:
        e = by_id[eid]
        sources.append(
            {
                "id": eid,
                "type": e.type.value,
                "player": roster.get(e.player_id.root) if e.player_id else None,
                "clock": render_minute(e.t.root, "en", int(e.period.value))[0],
            }
        )
    frame = store.freeze_frame(match_id, anchor)
    return {
        "kind": beat.kind.value,
        "label": beat.label,
        "clock": clock_at(events, beat.t_detect.root),
        "t": beat.t_detect.root,
        "facts": [
            {"id": f["id"], "label": f["label"], "text": f["display"]["en"][0]}
            for f in bundle["facts"]
        ],
        "sources": sources,
        "freeze": (
            frame.model_dump(mode="json", by_alias=True, exclude_none=True)
            if frame
            else None
        ),
    }


def build_web(
    results: Json,
    fixtures: list[Fixture],
    narrator_deployment: str,
    next_up: list[Json],
) -> Json:
    """Everything the Table and Compare pages draw, from a results file and the pack."""
    summary = results["summary"]
    ranks, order = ranks_of(summary)
    measured = {r["candidate"]: is_measured(r) for r in summary}
    wanted: dict[str, set[str]] = {}
    for c in results["claims"]:
        wanted.setdefault(c["fixture"], set()).add(c["beat"])

    meta = {f["id"]: f for f in results["fixtures"]}
    fixture_rows: list[Json] = []
    moments: Json = {}
    all_bundles: dict[str, Json] = {}
    clocks: dict[tuple[str, str], str] = {}
    for fixture in fixtures:
        if fixture.id not in meta:
            continue
        store, match_id = build_store_from_brief(fixture.make_brief())
        if match_id != meta[fixture.id]["match_id"]:
            raise SystemExit(
                f"{fixture.id}: the pack builds {match_id}, not the results' match"
            )
        events = sorted(store.events(match_id), key=lambda e: (e.t.root, e.seq))
        beats = {b.id.root: b for b in store.beats(match_id)}
        fixture_rows.append(
            {
                **meta[fixture.id],
                "traps": labelled_traps(meta[fixture.id]["traps"], events),
                "match_brief": json.loads(
                    fixture.make_brief().model_dump_json(
                        by_alias=True, exclude_none=True
                    )
                ),
                "trap_beats": trap_beats(fixture, list(beats.values())),
            }
        )
        moments[fixture.id] = {}
        beat_ids = sorted(
            wanted.get(fixture.id, ()), key=lambda b: beats[b].t_detect.root
        )
        bundles = asyncio.run(bundles_of(store, match_id, beat_ids))
        all_bundles[fixture.id] = bundles
        for beat_id in beat_ids:
            m = moment_of(store, match_id, beats[beat_id], bundles[beat_id], events)
            moments[fixture.id][beat_id] = m
            clocks[(fixture.id, beat_id)] = m["clock"]

    traps = frozenset(
        (f["id"], t["beat"]) for f in fixture_rows for t in f["trap_beats"]
    )
    worst = {
        r["candidate"]: worst_of(results["claims"], r["candidate"], traps)
        if measured[r["candidate"]]
        else None
        for r in summary
    }
    web: Json = {
        "pack": results["pack"],
        "results": results,
        "ranks": ranks,
        "order": order,
        "measured": measured,
        "worst": worst,
        "trap_record": {
            r["candidate"]: trap_record_of(results["claims"], r["candidate"], traps)
            for r in summary
        },
        "fail_top": {r["candidate"]: fail_top_of(r["fail_profile"]) for r in summary},
        "picks": picks_of(summary),
        "points": dict(POINTS),
        "live_narrator": live_narrator_of(results["candidates"], narrator_deployment),
        "fixtures": fixture_rows,
        "moments": moments,
        "claim_clock": {
            str(i): clocks[(c["fixture"], c["beat"])]
            for i, c in enumerate(results["claims"])
        },
        "claim_numbers": {
            str(i): numbers_of(c, all_bundles[c["fixture"]][c["beat"]])
            for i, c in enumerate(results["claims"])
        },
        "next_up": next_up,
    }
    return web


def shrink_to_limit(web: Json, limit: int = SIZE_LIMIT) -> list[str]:
    """If the file is over `limit` bytes, drop `freeze` from the beats that are neither a trap beat
    nor any candidate's worst moment. Returns what was dropped, for the log."""
    if len(json.dumps(web, ensure_ascii=False).encode()) <= limit:
        return []
    keep = {(f["id"], t["beat"]) for f in web["fixtures"] for t in f["trap_beats"]} | {
        (w["fixture"], w["beat"]) for w in web["worst"].values() if w
    }
    dropped = []
    for fid, beats in web["moments"].items():
        for bid, m in beats.items():
            if (fid, bid) not in keep and m["freeze"] is not None:
                m["freeze"] = None
                dropped.append(f"{fid}/{bid}")
    return dropped


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("results", type=Path, help="a trials results JSON")
    args = parser.parse_args()
    results: Json = json.loads(args.results.read_text("utf-8"))
    pack, fixtures = load_pack(PACK_PATH)
    if pack != results["pack"]:
        raise SystemExit(f"the results are for {results['pack']}, the pack is {pack}")
    narrator = str(load_models()["narrator"]["deployment"])
    next_up = yaml.safe_load(NEXT_UP_PATH.read_text("utf-8")) or []
    web = build_web(results, fixtures, narrator, next_up)
    dropped = shrink_to_limit(web)
    if dropped:
        print(f"over {SIZE_LIMIT} bytes: dropped freeze frames of {len(dropped)} beats")
    TrialsWeb.model_validate(web)  # the contract, before anything is written
    stem = args.results.stem  # pack-v1 or pack-v1-smoke
    WEB_FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    out = WEB_FIXTURES_DIR / f"web-{stem}.json"
    out.write_text(json.dumps(web, indent=1, ensure_ascii=False) + "\n", "utf-8")
    print(f"{out} {out.stat().st_size} bytes", file=sys.stdout)


if __name__ == "__main__":
    main()
