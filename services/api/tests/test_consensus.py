"""Corrections by consensus, with fake models: no model calls."""

import asyncio
import json
import threading
from pathlib import Path
from typing import Any

import pytest
from agent_fakes import (
    REWRITE,
    ConsensusJudge,
    FakeModel,
    RewritingNarrator,
    agent_runtime,
)
from agents.budget import budget
from api.agents_runtime import MatchRun
from api.live import run_live
from contracts.models import Audit
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012
from test_agents_live import SHORT_MATCH_S, SPEED, ScaledPacer, brief, claims_of, dump

ROOT = Path(__file__).resolve().parents[3]
FIRST_DRAFT = "A moment worth a look."


@pytest.fixture(autouse=True)
def fresh_budget(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.delenv("DAILY_TOKEN_CAP", raising=False)
    budget._used.clear()
    budget._split.clear()
    yield
    budget._used.clear()
    budget._split.clear()


def stream_validator() -> Draft202012Validator:
    schemas = {
        p.name: json.loads(p.read_text())
        for p in (ROOT / "schemas").glob("*.schema.json")
    }
    registry: Registry[Any] = Registry()
    for s in schemas.values():
        registry = registry.with_resource(
            str(s["$id"]), Resource.from_contents(s, DRAFT202012)
        )
    return Draft202012Validator(
        schemas["stream_message.schema.json"], registry=registry
    )


CORRECTION_TIMEOUT_S = 30.0  # as long as the stream's own hold at full time


class CorrectionWatch:
    """Set once the run has made a correction; the test waits on the correction, not on counters."""

    def __init__(self, run: MatchRun) -> None:
        self.seen = asyncio.Event()
        self._unsubscribe = run.subscribe_corrections(
            lambda _claim, _span: self.seen.set()
        )

    async def wait(self) -> None:
        try:
            await asyncio.wait_for(self.seen.wait(), CORRECTION_TIMEOUT_S)
        except TimeoutError:
            pytest.fail(
                f"no correction was made within {CORRECTION_TIMEOUT_S:.0f} s of the stream ending: "
                "the audit or the judge's re-check never finished"
            )

    def close(self) -> None:
        self._unsubscribe()


async def play_with_audits(
    run: MatchRun, store: Any, gate: threading.Event
) -> list[dict[str, Any]]:
    """The short match, with the audits held back until the stream is well under way. The stream
    holds full time for the audits and corrections still running, so they are done when it ends."""
    out: list[dict[str, Any]] = []
    async for m in run_live(
        brief(),
        SPEED,
        pacer=ScaledPacer(),
        store=store,
        agents=run,
        until_s=SHORT_MATCH_S,
    ):
        out.append(dump(m))
        if len(out) == 400:
            gate.set()
    return out


def scenario_run(
    *,
    judge: ConsensusJudge,
    auditor_agrees: bool = False,
    expect_correction: bool = False,
    check: Any,
) -> None:
    async def go() -> None:
        gate = threading.Event()
        auditor = FakeModel("judge-grok", supported=auditor_agrees, gate=gate)
        async with agent_runtime(
            narrator=RewritingNarrator("fake-narrator"), judge=judge, auditor=auditor
        ) as (rt, store):
            run = rt.match(brief())
            watch = CorrectionWatch(run)
            try:
                out = await play_with_audits(run, store, gate)
                if expect_correction:
                    await watch.wait()
                await check(run, store, out)
            finally:
                watch.close()

    asyncio.run(go())


def test_a_correction_replaces_the_text_and_keeps_the_previous_one() -> None:
    judge = ConsensusJudge(agrees_on_recheck=True)

    async def check(run: MatchRun, store: Any, out: list[dict[str, Any]]) -> None:
        stored = {
            c.id.root: c for cs in store.claims(run.match_id).values() for c in cs
        }
        corrected = [c for c in stored.values() if c.correction is not None]
        assert corrected
        for c in corrected:
            assert c.verdict.value == "rephrased" and c.text == REWRITE
            assert c.correction is not None
            assert c.correction.previous_text == FIRST_DRAFT
            assert c.correction.by == ["judge-grok", "fake-judge"]
            assert c.correction.reason == "Says more than the facts."
            assert c.draft_text == FIRST_DRAFT and c.reason
            assert c.audit is None  # the audit was of the old text
        sent = [m for m in claims_of(out, "verdict") if "correction" in m["data"]]
        assert sent
        validate = stream_validator()
        for m in sent:
            validate.validate(m)
            assert m["data"]["correction"]["previous_text"] == FIRST_DRAFT
            assert m["data"]["text"] == REWRITE and m["data"]["verdict"] == "rephrased"
        summary = run.audit_summary()
        assert len(summary["corrections"]) == len(corrected)
        assert summary["corrections"][0]["previous_text"] == FIRST_DRAFT
        assert summary["unresolved"] == []
        assert summary["agreement_rate"] == 0.0
        assert summary["agreement_rate_after_corrections"] == 1.0
        # a claim is reviewed once: the same disagreement again changes nothing
        before = len(run.ledger.corrections)
        claim, audit, _ = run.ledger.audited[0]
        await run._correct(claim, audit)
        assert len(run.ledger.corrections) == before

    scenario_run(judge=judge, expect_correction=True, check=check)


def test_a_rewrite_that_fails_the_check_blocks_the_claim_with_its_correction() -> None:
    judge = ConsensusJudge(agrees_on_recheck=True, refuses_rewrite=True)

    async def check(run: MatchRun, store: Any, out: list[dict[str, Any]]) -> None:
        stored = [c for cs in store.claims(run.match_id).values() for c in cs]
        blocked = [c for c in stored if c.correction is not None]
        assert blocked
        for c in blocked:
            assert c.verdict.value == "blocked" and c.reason
            assert (
                c.correction is not None and c.correction.previous_text == FIRST_DRAFT
            )
        sent = [m for m in claims_of(out, "verdict") if "correction" in m["data"]]
        assert sent and all(m["data"]["verdict"] == "blocked" for m in sent)
        validator = stream_validator()
        for m in sent:
            validator.validate(m)

    scenario_run(judge=judge, expect_correction=True, check=check)


def test_a_recheck_that_still_disagrees_with_the_auditor_changes_nothing() -> None:
    judge = ConsensusJudge(agrees_on_recheck=False)

    async def check(run: MatchRun, store: Any, out: list[dict[str, Any]]) -> None:
        assert run.ledger.pending == 0, "full time did not wait for the re-check"
        assert judge.rechecks > 0
        stored = [c for cs in store.claims(run.match_id).values() for c in cs]
        assert all(c.correction is None for c in stored)
        assert all(c.text == FIRST_DRAFT for c in stored)
        assert not [
            m for m in claims_of(out, "verdict", "claim") if "correction" in m["data"]
        ]
        summary = run.audit_summary()
        assert summary["corrections"] == []
        assert len(summary["unresolved"]) == judge.rechecks
        assert summary["agreement_rate_after_corrections"] == summary["agreement_rate"]
        log = [e["audit"] for e in run.producer_log() if "audit" in e]
        assert any("keeps it" in line for line in log)

    scenario_run(judge=judge, check=check)


def test_an_agreeing_auditor_never_triggers_a_recheck() -> None:
    judge = ConsensusJudge(agrees_on_recheck=True)

    async def check(run: MatchRun, store: Any, out: list[dict[str, Any]]) -> None:
        assert run.ledger.audited
        assert judge.rechecks == 0
        assert run.ledger.corrections == [] and run.ledger.unresolved == []

    scenario_run(judge=judge, auditor_agrees=True, check=check)


def test_corrections_stop_when_auditing_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    judge = ConsensusJudge(agrees_on_recheck=True)

    async def go() -> None:
        async with agent_runtime(
            narrator=RewritingNarrator("fake-narrator"),
            judge=judge,
            auditor=FakeModel("judge-grok", supported=False),
        ) as (rt, store):
            run = rt.match(brief())
            await play_with_audits(run, store, threading.Event())
            before = len(run.ledger.corrections)
            claim, _, _ = run.ledger.audited[-1]
            run._corrected.discard(claim.id.root)
            monkeypatch.setenv("DAILY_TOKEN_CAP", "1")  # the day's tokens are spent
            assert budget.auditing_stopped
            await run._correct(
                claim,
                Audit.model_validate(
                    {
                        "deployment": "judge-grok",
                        "outcome": "disagree",
                        "problem": "overclaim",
                        "reason": "x",
                    }
                ),
            )
            assert len(run.ledger.corrections) == before
            assert judge.rechecks == before + len(run.ledger.unresolved)

    asyncio.run(go())


def test_a_correction_that_finishes_after_the_last_playback_tick_is_still_sent() -> (
    None
):
    """The audits are held until playback reaches full time, so every audit, re-check and
    correction finishes after the last tick. The stream must hold full time for them."""
    judge = ConsensusJudge(agrees_on_recheck=True, refuses_rewrite=True)

    async def go() -> None:
        gate = threading.Event()
        auditor = FakeModel("judge-grok", supported=False, gate=gate)
        async with agent_runtime(
            narrator=RewritingNarrator("fake-narrator"), judge=judge, auditor=auditor
        ) as (rt, store):
            released_at: list[int] = []
            out: list[dict[str, Any]] = []
            real_set_playback = store.set_playback

            def release_at_full_time(match_id: str, t: float) -> None:
                real_set_playback(match_id, t)
                if t >= SHORT_MATCH_S and not gate.is_set():
                    released_at.append(
                        len(out)
                    )  # the full-time tick: no audit has run yet
                    gate.set()

            store.set_playback = release_at_full_time
            run = rt.match(brief())
            watch = CorrectionWatch(run)
            try:
                async for m in run_live(
                    brief(),
                    SPEED,
                    pacer=ScaledPacer(),
                    store=store,
                    agents=run,
                    until_s=SHORT_MATCH_S,
                ):
                    out.append(dump(m))
                await watch.wait()
            finally:
                watch.close()
            assert released_at, "playback never reached the full-time tick"
            assert run.ledger.corrections
            sent = [m for m in claims_of(out, "verdict") if "correction" in m["data"]]
            assert sent, "the correction landed after full time and was never sent"
            full_time = next(
                i
                for i, m in enumerate(out)
                if m["type"] == "status" and m["data"]["state"] == "full_time"
            )
            assert all(out.index(m) < full_time for m in sent)
            seqs = [m["seq"] for m in out]
            assert seqs == list(range(seqs[0], seqs[0] + len(seqs)))

    asyncio.run(go())
