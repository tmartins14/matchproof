"""The agent workflow on the live stream, with fake models (no model calls)."""

import asyncio
import threading
from typing import Any

import pytest
from agent_fakes import FakeModel, agent_runtime, rate_limited
from agents.auditor import Auditor
from agents.budget import budget
from agents.llm_client import LlmError
from api.agents_runtime import DownRun, MatchRun, SessionServer
from api.live import PAUSED_TEXT, UNAVAILABLE_TEXT, run_live
from api.telemetry import configure_telemetry
from contracts.models import MatchBrief, StreamMessage
from sim.brief import DEFAULT_AWAY, DEFAULT_HOME, make_brief

configure_telemetry()
FINAL = {"verified", "rephrased", "blocked", "delayed"}
SPEED = 6
SHORT_MATCH_S = 12 * 60  # the live-agent tests play the first 12 match minutes, not 95
SCALE = (
    1 / 100
)  # real seconds per scheduled second: focus windows and holds still take a moment


class ScaledPacer:
    """A clock that really waits, a hundredth of the time, so work in flight can finish."""

    def __init__(self) -> None:
        self._origin = asyncio.get_event_loop().time()

    def now(self) -> float:
        return 0.0

    async def sleep_until(self, real_t: float) -> None:
        wait = self._origin + real_t * SCALE - asyncio.get_event_loop().time()
        await asyncio.sleep(max(wait, 0.0))


class QuiescentPacer(ScaledPacer):
    """Playback does not pass a message's turn until the agents have no pending work: every claim
    is settled before its beat airs, whatever the machine's speed."""

    def __init__(self, run: MatchRun | DownRun) -> None:
        super().__init__()
        self._run = run

    async def sleep_until(self, real_t: float) -> None:
        await super().sleep_until(real_t)
        if isinstance(self._run, MatchRun):
            await self._run.quiesce()


def brief() -> MatchBrief:
    return make_brief(DEFAULT_HOME, DEFAULT_AWAY, "red_card_flip", 3)


def dump(msg: StreamMessage) -> dict[str, Any]:
    out: dict[str, Any] = msg.model_dump(mode="json", by_alias=True, exclude_none=True)
    return out


async def play(
    run: MatchRun | DownRun,
    store: Any,
    pacer: Any = None,
    until_s: float | None = SHORT_MATCH_S,
) -> list[dict[str, Any]]:
    """The (short) match. The default pacer waits for the agents; pass a plain one to race them."""
    return [
        dump(m)
        async for m in run_live(
            brief(),
            SPEED,
            pacer=pacer or QuiescentPacer(run),
            store=store,
            agents=run,
            until_s=until_s,
        )
    ]


@pytest.fixture(autouse=True)
def fresh_budget(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.delenv("DAILY_TOKEN_CAP", raising=False)
    budget._used.clear()
    yield
    budget._used.clear()


def claims_of(messages: list[dict[str, Any]], *kinds: str) -> list[dict[str, Any]]:
    return [m for m in messages if m["type"] in kinds]


def test_claims_follow_their_beats_and_verdicts_follow_their_claims() -> None:
    async def scenario() -> None:
        async with agent_runtime() as (rt, store):
            run = rt.match(brief())
            messages = await play(run, store)
            assert [m["seq"] for m in messages] == list(range(len(messages)))
            beat_at = {
                m["data"]["id"]: i
                for i, m in enumerate(messages)
                if m["type"] == "beat"
            }
            first_claim: dict[str, int] = {}
            for i, m in enumerate(messages):
                if m["type"] == "claim":
                    first_claim.setdefault(m["data"]["id"], i)
                    assert i > beat_at[m["data"]["beat_id"]]
                if m["type"] == "verdict":
                    assert m["data"]["id"] in first_claim, "verdict before its claim"
                    assert i > first_claim[m["data"]["id"]]
            assert first_claim, "no claims reached the stream"
            for m in claims_of(messages, "verdict"):
                assert m["data"]["verdict"] in FINAL
                assert m["span_id"]
            # every claim ends with a verdict, either on the claim or in a verdict message
            final: dict[str, str] = {}
            for m in claims_of(messages, "claim", "verdict"):
                final[m["data"]["id"]] = m["data"]["verdict"]
            assert set(final.values()) <= FINAL

    asyncio.run(scenario())


def test_claims_checked_before_air_are_sent_with_their_final_verdict() -> None:
    async def scenario() -> None:
        async with agent_runtime() as (rt, store):
            messages = await play(rt.match(brief()), store)
            sent = claims_of(messages, "claim")
            assert sent
            assert all(m["data"]["verdict"] in FINAL for m in sent)
            assert all("latency_ms" in m["data"]["checker"] for m in sent)
            assert claims_of(messages, "verdict") == []

    asyncio.run(scenario())


def test_a_slow_judge_gives_checking_then_verdict() -> None:
    async def scenario() -> None:
        async with agent_runtime(judge=FakeModel("slow-judge", delay_s=1.0)) as (
            rt,
            store,
        ):
            run = rt.match(brief())
            messages = await play(run, store, ScaledPacer())
            checking = [
                m
                for m in claims_of(messages, "claim")
                if m["data"]["verdict"] == "checking"
            ]
            assert checking
            index = {id(m): i for i, m in enumerate(messages)}
            for c in checking:
                later = [
                    m
                    for m in claims_of(messages, "verdict")
                    if m["data"]["id"] == c["data"]["id"]
                ]
                assert len(later) == 1
                assert later[0]["data"]["verdict"] in FINAL
                assert index[id(later[0])] > index[id(c)]
            states = [m["data"]["state"] for m in messages if m["type"] == "status"]
            assert states[-1] == "full_time"

    asyncio.run(scenario())


def test_ranks_run_from_one_in_the_order_of_the_feed() -> None:
    async def scenario() -> None:
        async with agent_runtime() as (rt, store):
            messages = await play(rt.match(brief()), store)
            ranks = [
                m["data"]["rank"]
                for m in messages
                if m["type"] == "beat" and "rank" in m["data"]
            ]
            assert ranks == list(range(1, len(ranks) + 1)) and ranks
            skipped = [
                m for m in messages if m["type"] == "beat" and "rank" not in m["data"]
            ]
            skipped_ids = {m["data"]["id"] for m in skipped}
            assert not any(
                m["data"]["beat_id"] in skipped_ids
                for m in claims_of(messages, "claim")
            )

    asyncio.run(scenario())


def test_a_failing_judge_leaves_claims_delayed_and_the_match_finishes() -> None:
    async def scenario() -> None:
        judge = FakeModel("broken-judge", error=LlmError("APITimeoutError"))
        async with agent_runtime(judge=judge) as (rt, store):
            messages = await play(rt.match(brief()), store)
            verdicts = {
                m["data"]["verdict"] for m in claims_of(messages, "claim", "verdict")
            } - {"checking"}
            assert verdicts == {"delayed"}
            states = [m["data"]["state"] for m in messages if m["type"] == "status"]
            assert states[-1] == "full_time"

    asyncio.run(scenario())


def test_a_failing_narrator_streams_beats_without_claims() -> None:
    async def scenario() -> None:
        narrator = FakeModel("broken", error=LlmError("APITimeoutError"))
        async with agent_runtime(narrator=narrator) as (rt, store):
            messages = await play(rt.match(brief()), store)
            assert claims_of(messages, "beat")
            assert claims_of(messages, "claim", "verdict") == []

    asyncio.run(scenario())


def test_the_token_cap_pauses_narration_and_stops_model_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DAILY_TOKEN_CAP", "100")
    budget.add("narrator", 100)

    async def scenario() -> None:
        narrator, judge, producer = FakeModel(), FakeModel(), FakeModel()
        async with agent_runtime(narrator=narrator, judge=judge, producer=producer) as (
            rt,
            store,
        ):
            messages = await play(rt.match(brief()), store)
            notices = [
                m["data"]["message"]
                for m in messages
                if m["type"] == "status" and m["data"]["state"] == "notice"
            ]
            assert notices == [PAUSED_TEXT]
            assert claims_of(messages, "claim", "verdict") == []
            assert claims_of(messages, "beat")
            assert narrator.calls == judge.calls == producer.calls == 0

    asyncio.run(scenario())


def test_a_workflow_that_is_down_streams_beats_and_says_so() -> None:
    async def scenario() -> None:
        async with agent_runtime() as (_, store):
            messages = await play(DownRun(), store)
        notices = [
            m["data"]["message"]
            for m in messages
            if m["type"] == "status" and m["data"]["state"] == "notice"
        ]
        assert notices == [UNAVAILABLE_TEXT]
        assert claims_of(messages, "beat")
        assert claims_of(messages, "claim", "verdict") == []

    asyncio.run(scenario())


def test_every_claim_carries_a_trace_id() -> None:
    async def scenario() -> None:
        async with agent_runtime() as (rt, store):
            run = rt.match(brief())
            messages = await play(run, store)
            ids = {
                m["data"]["checker"]["trace_id"]
                for m in claims_of(messages, "claim", "verdict")
                if m["data"]["verdict"] != "checking"
            }
            assert len(ids) == 1  # one trace for the match run
            assert all(len(t) == 32 and t != "0" * 32 for t in ids)
            for claims in store.claims(run.match_id).values():
                assert all(c.checker and c.checker.trace_id for c in claims)

    asyncio.run(scenario())


def test_a_disagreeing_auditor_never_changes_a_verdict() -> None:
    async def scenario() -> None:
        auditor = FakeModel("judge-grok", supported=False)
        async with agent_runtime(auditor=auditor) as (rt, store):
            run = rt.match(brief())
            messages = await play(run, store)
            # audits are not waited for; give the ones in flight a moment
            for _ in range(100):
                if not run.ledger.pending and run.ledger.audited:
                    break
                await asyncio.sleep(0.05)
            before = {
                m["data"]["id"]: m["data"]["verdict"]
                for m in claims_of(messages, "claim", "verdict")
                if m["data"]["verdict"] != "checking"
            }
            stored = {
                c.id.root: c for cs in store.claims(run.match_id).values() for c in cs
            }
            audited = {cid: c for cid, c in stored.items() if c.audit is not None}
            assert audited
            for cid, c in audited.items():
                assert c.audit is not None and c.audit.outcome.value == "disagree"
                if cid in before:
                    assert c.verdict.value == before[cid]
            summary = run.audit_summary()
            assert summary["claims_audited"] == len(audited)
            assert summary["agreement_rate"] == 0.0
            assert len(summary["disagreements"]) == len(audited)
            assert summary["disagreements"][0]["auditor"]["reason"]
            log = [e["audit"] for e in run.producer_log() if "audit" in e]
            # each disagreement is logged, and then the re-check that left it unresolved
            assert len(log) == 2 * len(audited)
            assert all("disagrees" in line for line in log)

    asyncio.run(scenario())


def test_an_audit_of_a_claim_on_screen_is_sent_as_a_verdict_with_the_same_verdict() -> (
    None
):
    async def scenario() -> None:
        # the stream is over before the slow audit lands, so replay it from a live subscriber
        gate = threading.Event()
        auditor = FakeModel("judge-grok", supported=False, gate=gate)
        async with agent_runtime(auditor=auditor) as (rt, store):
            run = rt.match(brief())
            out: list[dict[str, Any]] = []

            async def watch() -> None:
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
                        gate.set()  # release the audits while the stream is still going

            await watch()
            audits = [m for m in claims_of(out, "verdict") if "audit" in m["data"]]
            assert audits
            posted = {
                m["data"]["id"]: m["data"]["verdict"]
                for m in claims_of(out, "claim")
                if m["data"]["verdict"] != "checking"
            }
            for m in audits:
                assert m["data"]["audit"]["outcome"] == "disagree"
                if m["data"]["id"] in posted:
                    assert m["data"]["verdict"] == posted[m["data"]["id"]]

    asyncio.run(scenario())


def test_audits_never_delay_a_claim(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "api.live.POST_FULL_TIME_S", 0.2
    )  # a stalled auditor keeps the stream open after full time

    async def scenario() -> None:
        gate = threading.Event()  # the auditor answers only when released
        auditor = FakeModel("judge-grok", gate=gate)
        async with agent_runtime(auditor=auditor) as (rt, store):
            run = rt.match(brief())
            messages = await asyncio.wait_for(play(run, store), timeout=60)
            assert claims_of(messages, "claim")
            assert all(
                m["data"]["verdict"] in FINAL | {"checking"}
                for m in claims_of(messages, "claim")
            )
            assert (
                run.ledger.pending > 0 or auditor.started > 0
            )  # audits were still waiting
            gate.set()

    asyncio.run(scenario())


def test_auditing_stops_before_narration_when_the_token_cap_nears(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DAILY_TOKEN_CAP", "1000000")
    budget.add("narrator", 950_000)  # past the audit line, short of the cap

    async def scenario() -> None:
        narrator, auditor = FakeModel(), FakeModel("judge-grok")
        async with agent_runtime(narrator=narrator, auditor=auditor) as (rt, store):
            run = rt.match(brief())
            messages = await play(run, store)
            await asyncio.sleep(0.2)
            assert narrator.calls > 0
            assert claims_of(messages, "claim")
            assert auditor.started == 0
            assert run.audit_summary()["skipped_for_token_cap"] > 0

    asyncio.run(scenario())


def test_a_429_gives_unavailable_after_one_retry() -> None:
    async def scenario() -> None:
        async with agent_runtime() as (rt, store):
            run = rt.match(brief())
            await play(run, store)
            claim = next(c for cs in store.claims(run.match_id).values() for c in cs)
            limited = FakeModel("judge-grok", error=rate_limited())
            auditor = Auditor(limited, rt.server, retry_pause_s=0.0)
            result = await auditor.audit(run.match_id, claim)
            assert result.outcome.value == "unavailable"
            assert limited.started == 2  # the call and one retry
            stored = next(
                c
                for cs in store.claims(run.match_id).values()
                for c in cs
                if c.id.root == claim.id.root
            )
            assert stored.audit is not None
            assert stored.audit.outcome.value == "unavailable"

    asyncio.run(scenario())


def test_session_server_raises_on_a_tool_error() -> None:
    async def scenario() -> None:
        async with agent_runtime() as (rt, _):
            assert isinstance(rt.server, SessionServer)
            with pytest.raises(ValueError, match="Unknown match"):
                await rt.server.call_tool("get_brief", {"match_id": "m-nope"})

    asyncio.run(scenario())


@pytest.mark.slow
def test_the_full_match_ends_with_every_claim_settled() -> None:
    async def scenario() -> None:
        async with agent_runtime() as (rt, store):
            run = rt.match(brief())
            messages = await play(run, store, until_s=None)
            states = [m["data"]["state"] for m in messages if m["type"] == "status"]
            assert states[-1] == "full_time"
            final: dict[str, str] = {}
            for m in claims_of(messages, "claim", "verdict"):
                final[m["data"]["id"]] = m["data"]["verdict"]
            assert final and set(final.values()) <= FINAL
            assert any(m["type"] == "beat" and m["t"] > SHORT_MATCH_S for m in messages)

    asyncio.run(scenario())
