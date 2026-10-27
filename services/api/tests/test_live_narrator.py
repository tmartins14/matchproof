"""?narrator=<id> on the stream: one match's Narrator client differs, the referee is shared."""

import asyncio
from collections import Counter
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from agent_fakes import FakeModel, agent_runtime
from api import main
from api.agents_runtime import AgentRuntime, MatchRun
from api.telemetry import configure_telemetry
from contracts.models import StreamMessage
from test_agents_live import brief, claims_of, fresh_budget, play  # noqa: F401

configure_telemetry()
LIVE = ["alpha", "beta"]


def unwrapped(run: MatchRun) -> Any:
    """The fake behind the metering wrapper of the run's Narrator."""
    return run.deps.narrator._inner  # type: ignore[attr-defined]


def runtime_with(rt: AgentRuntime, fakes: dict[str, FakeModel]) -> AgentRuntime:
    rt._narrator_for = lambda candidate: fakes[candidate]
    return rt


def test_the_default_match_uses_the_shared_narrator_and_says_nothing() -> None:
    async def scenario() -> None:
        shared = FakeModel("shared")
        async with agent_runtime(narrator=shared) as (rt, store):
            run = rt.match(brief())
            assert run.narrator_id is None
            messages = await play(run, store)
            assert shared.calls > 0
            assert all(
                "narrator" not in m["data"] for m in claims_of(messages, "status")
            )

    asyncio.run(scenario())


def test_an_allowed_id_uses_that_client_and_is_named_on_the_first_status() -> None:
    async def scenario() -> None:
        shared, alpha = FakeModel("shared"), FakeModel("alpha")
        async with agent_runtime(narrator=shared) as (rt, store):
            runtime_with(rt, {"alpha": alpha})
            run = rt.match(brief(), "alpha")
            assert run.narrator_id == "alpha"
            assert run.span.attributes["matchproof.narrator"] == "alpha"  # type: ignore[attr-defined]
            messages = await play(run, store)
            statuses = claims_of(messages, "status")
            assert statuses[0]["data"]["narrator"] == "alpha"
            assert sum("narrator" in s["data"] for s in statuses) == 1
            assert alpha.calls > 0 and shared.calls == 0

    asyncio.run(scenario())


def test_two_concurrent_matches_with_different_narrators_do_not_share_a_client() -> (
    None
):
    async def scenario() -> None:
        fakes = {"alpha": FakeModel("alpha"), "beta": FakeModel("beta")}
        shared, judge = FakeModel("shared"), FakeModel("judge")
        async with agent_runtime(narrator=shared, judge=judge) as (rt, _store):
            runtime_with(rt, fakes)
            one = rt.match(brief(), "alpha")
            other_brief = brief().model_copy(update={"match_id": "m-other"})
            two = rt.match(other_brief, "beta")
            assert unwrapped(one) is fakes["alpha"]
            assert unwrapped(two) is fakes["beta"]
            assert one.deps.narrator is not two.deps.narrator
            assert one.deps.judge is two.deps.judge is rt.judge  # the referee is shared

    asyncio.run(scenario())


async def fake_run_live(*args: Any, **kwargs: Any) -> AsyncIterator[StreamMessage]:
    yield StreamMessage.model_validate(
        {"seq": 0, "type": "status", "t": 0, "data": {"state": "live"}}
    )


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> Any:
    seen: list[dict[str, Any]] = []

    async def spy(*args: Any, **kwargs: Any) -> AsyncIterator[StreamMessage]:
        seen.append(kwargs)
        async for m in fake_run_live():
            yield m

    monkeypatch.setattr(main, "run_live", spy)
    monkeypatch.setattr(main, "live_narrator_ids", lambda: LIVE)
    monkeypatch.setattr(main, "_streams", Counter())
    return seen


def get(path: str, method: str = "get", **kw: Any) -> httpx.Response:
    async def go() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main.app, client=("203.0.113.9", 1)),
            base_url="http://t",
        ) as c:
            return await getattr(c, method)(path, **kw)

    return asyncio.run(go())


def new_match() -> str:
    made = get("/matches", "post", json={"story": "late_comeback", "seed": 1})
    return str(made.json()["match_id"])


def test_no_narrator_param_streams_as_before(api: list[dict[str, Any]]) -> None:
    r = get(f"/matches/{new_match()}/stream")
    assert r.status_code == 200
    assert api[0]["narrator"] is None


def test_a_live_ready_id_is_passed_to_the_stream(api: list[dict[str, Any]]) -> None:
    r = get(f"/matches/{new_match()}/stream?narrator=alpha")
    assert r.status_code == 200
    assert api[0]["narrator"] == "alpha"


@pytest.mark.parametrize("bad", ["nope", "grok-4.7", ""])
def test_an_unknown_or_not_live_ready_id_is_422(
    api: list[dict[str, Any]], bad: str
) -> None:
    r = get(f"/matches/{new_match()}/stream?narrator={bad}")
    assert r.status_code == 422
    assert api == []
