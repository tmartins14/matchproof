import asyncio
import re
from pathlib import Path
from typing import Any

import agents
from agents.checker import Checker
from agents.llm_client import LlmError
from agents.narrator import DraftClaim, Revision, narrate
from agents.pipeline import BeatRun, Deps, narrate_and_check, tool_result
from agents.workflow import run_beat_workflow
from contracts.models import Claim, Fact
from fakes import FakeChat
from helpers import fill
from mcp_match import InMemoryMatchStore, build_server

GOOD = {"supported": True, "problem": None, "reason": "Matches."}


def setup() -> tuple[InMemoryMatchStore, str, str, str]:
    store = InMemoryMatchStore()
    match_id = fill(store, "red_card_flip", 3)
    beat = next(b for b in store.beats(match_id) if b.kind.value == "card")
    fact = next(
        f
        for f in (store.registry(match_id).get(x.root) for x in beat.fact_ids)
        if f.name.endswith(".players_after")
    )
    return store, match_id, beat.id.root, fact.id.root


def replies(fact_id: str, shown: str, retry_ok: bool) -> list[dict[str, Any]]:
    good = {"text": f"Ashford Vale are down to {shown} players.", "fact_ids": [fact_id]}
    bad = {
        "text": f"Ashford Vale are down to {shown} players after a brilliant tackle.",
        "fact_ids": [fact_id],
    }
    fixed = {
        "text": f"Ashford Vale play on with {shown} players.",
        "fact_ids": [fact_id],
    }
    return [{"claims": [good, bad]}, {"claims": [fixed if retry_ok else bad]}]


def shown_of(store: InMemoryMatchStore, match_id: str, fact_id: str) -> str:
    return store.registry(match_id).get(fact_id).display.en[0]


def comparable(claims: list[Claim]) -> list[dict[str, Any]]:
    out = []
    for c in claims:
        d = c.model_dump(mode="json", by_alias=True, exclude_none=True)
        d["checker"].pop("latency_ms", None)
        d["checker"].pop("trace_id", None)  # only the workflow runs inside a trace
        out.append(d)
    return out


def by_checker(
    store: InMemoryMatchStore,
    match_id: str,
    beat_id: str,
    narrator: FakeChat,
    judge: FakeChat,
) -> list[Claim]:
    """The reference: the Checker's own check_beat, as the workflow's steps are meant to equal it."""
    server = build_server(store, writable=False)

    async def go() -> list[Claim]:
        bundle = tool_result(
            await server.call_tool(
                "get_beat_bundle", {"match_id": match_id, "beat_id": beat_id}
            )
        )
        brief = tool_result(await server.call_tool("get_brief", {"match_id": match_id}))
        teams = {"home": brief["home"]["name"], "away": brief["away"]["name"]}
        names = {p["name"] for s in ("home", "away") for p in brief[s]["players"]}
        facts = {
            f["id"]: Fact.model_validate({k: v for k, v in f.items() if k != "label"})
            for f in bundle["facts"]
        }
        drafts = narrate(narrator, bundle, "fan", teams=teams).value.claims

        def again(rev: Revision) -> list[DraftClaim]:
            return narrate(
                narrator, bundle, "fan", teams=teams, revise=rev
            ).value.claims

        checked = Checker(judge).check_beat(
            drafts,
            facts,
            beat_id=beat_id,
            lang="en",
            teams=teams,
            beat_kind=bundle["beat"]["kind"],
            beat_label=bundle["beat"]["label"],
            labels={f["id"]: f["label"] for f in bundle["facts"]},
            names=names,
            renarrate=again,
        )
        return [c.claim for c in checked]

    return asyncio.run(go())


def test_workflow_equals_the_checkers_own_run() -> None:
    store, match_id, beat_id, fact_id = setup()
    shown = shown_of(store, match_id, fact_id)
    for retry_ok in (True, False):
        ref = by_checker(
            store,
            match_id,
            beat_id,
            FakeChat(list(replies(fact_id, shown, retry_ok))),
            FakeChat([GOOD, GOOD]),
        )
        fresh, mid, bid, fid = setup()
        deps = Deps(
            build_server(fresh, writable=True),
            FakeChat(list(replies(fid, shown_of(fresh, mid, fid), retry_ok))),
            FakeChat([GOOD, GOOD]),
        )
        claims = asyncio.run(narrate_and_check(mid, bid, "fan", deps=deps))
        assert comparable(claims) == comparable(ref)
        assert [c.verdict.value for c in claims] == (
            ["verified", "rephrased"] if retry_ok else ["verified", "blocked"]
        )


def test_the_retry_edge_is_taken_at_most_once() -> None:
    store, match_id, beat_id, fact_id = setup()
    narrator = FakeChat(replies(fact_id, shown_of(store, match_id, fact_id), False))
    deps = Deps(build_server(store, writable=True), narrator, FakeChat([GOOD]))
    claims = asyncio.run(narrate_and_check(match_id, beat_id, "fan", deps=deps))
    assert (
        len(narrator.prompts) == 2
    )  # the first draft and one retry; a third would have raised
    assert [c.verdict.value for c in claims] == ["verified", "blocked"]
    assert [c.checker.retries for c in claims if c.checker] == [0, 1]


def test_a_judge_that_fails_leaves_the_claims_delayed_and_the_beat_finishes() -> None:
    store, match_id, beat_id, fact_id = setup()
    good = {
        "claims": [
            {
                "text": f"Ashford Vale are down to {shown_of(store, match_id, fact_id)} players.",
                "fact_ids": [fact_id],
            }
        ]
    }
    deps = Deps(
        build_server(store, writable=True),
        FakeChat([good]),
        FakeChat([LlmError("APITimeoutError")]),
    )
    run = asyncio.run(run_beat_workflow(match_id, beat_id, "fan", deps=deps))
    assert [c.verdict.value for c in run.claims] == ["delayed"]
    assert len(store.claims(match_id)[beat_id]) == 1


def test_a_narrator_that_fails_gives_a_beat_with_no_claims() -> None:
    store, match_id, beat_id, _ = setup()
    deps = Deps(
        build_server(store, writable=True),
        FakeChat([LlmError("APITimeoutError")]),
        FakeChat([]),
    )
    run: BeatRun = asyncio.run(run_beat_workflow(match_id, beat_id, "fan", deps=deps))
    assert run.claims == []
    assert run.error == "Narrator: LlmError"


def test_agents_never_import_the_store_or_the_registry() -> None:
    root = Path(agents.__file__).parent
    pattern = re.compile(
        r"^\s*(?:from|import)\s+(?:mcp_match\.store|intel\.registry)\b", re.MULTILINE
    )
    for path in root.glob("*.py"):
        assert not pattern.search(path.read_text("utf-8")), path.name
    imported = "\n".join(p.read_text("utf-8") for p in root.glob("*.py"))
    assert "InMemoryMatchStore" not in imported
    assert "FactRegistry" not in imported
