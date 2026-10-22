import asyncio
import time
from collections import Counter
from typing import Any

import httpx
import pytest
from api import main
from api.live import (
    LOOKAHEAD_S,
    MAX_LIVE_STREAMS,
    SPEED_FASTEST,
    NoPacer,
    run_live,
)
from api.matchdata import (
    MCP_RPM_PER_CLIENT,
    RateLimiter,
    get_internal_server,
)
from contracts.models import StreamMessage
from fastapi.testclient import TestClient
from mcp.shared.memory import create_connected_server_and_client_session
from mcp_match import InMemoryMatchStore, build_server
from sim.brief import DEFAULT_AWAY, DEFAULT_HOME, make_brief

MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


def rpc(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def test_limiter_refuses_the_61st_request_in_a_minute_from_one_client() -> None:
    clock = Clock()
    limiter = RateLimiter(clock=clock)
    assert MCP_RPM_PER_CLIENT == 60
    for _ in range(MCP_RPM_PER_CLIENT):
        assert limiter.retry_after("203.0.113.1") is None
        clock.t += 0.5
    wait = limiter.retry_after("203.0.113.1")
    assert wait is not None and 1 <= wait <= 60
    assert limiter.retry_after("203.0.113.2") is None  # another client is not affected
    clock.t += 30.0  # the oldest requests are now a minute old
    assert limiter.retry_after("203.0.113.1") is None


def test_public_endpoint_serves_read_only_tools_and_limits_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MCP_ALLOWED_HOSTS", "testserver")
    monkeypatch.setattr(main.public_mcp, "limiter", RateLimiter(limit=3))
    with TestClient(main.app) as client:
        listed = client.post("/mcp", headers=MCP_HEADERS, json=rpc("tools/list"))
        assert listed.status_code == 200, listed.text
        names = {t["name"] for t in listed.json()["result"]["tools"]}
        assert "get_beat_bundle" in names and "put_claims" not in names
        missing = client.post(
            "/mcp",
            headers=MCP_HEADERS,
            json=rpc(
                "tools/call", {"name": "get_brief", "arguments": {"match_id": "x"}}
            ),
        )
        assert missing.json()["result"]["isError"] is True
        assert (
            client.post("/mcp", headers=MCP_HEADERS, json=rpc("tools/list")).status_code
            == 200
        )
        refused = client.post("/mcp", headers=MCP_HEADERS, json=rpc("tools/list"))
        assert refused.status_code == 429
        assert int(refused.headers["Retry-After"]) >= 1


def test_public_endpoint_rejects_a_host_that_is_not_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MCP_ALLOWED_HOSTS", raising=False)
    with TestClient(main.app) as client:  # the test client's host is "testserver"
        refused = client.post("/mcp", headers=MCP_HEADERS, json=rpc("tools/list"))
    assert refused.status_code == 421


def test_internal_server_is_writable_and_public_one_is_not() -> None:
    names = lambda s: {t.name for t in asyncio.run(s.list_tools())}
    store = InMemoryMatchStore()
    assert "put_claims" in names(get_internal_server(store))
    assert "put_claims" not in names(build_server(store, writable=False))


def test_a_fourth_concurrent_stream_gets_503_with_the_cached_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = asyncio.Event()

    async def held(*args: Any, **kwargs: Any) -> Any:
        yield StreamMessage.model_validate(
            {"seq": 0, "type": "status", "t": 0, "data": {"state": "live"}}
        )
        await release.wait()

    monkeypatch.setattr(main, "run_live", held)
    monkeypatch.setattr(main, "_streams", Counter())

    async def scenario() -> list[httpx.Response]:
        clients = [
            httpx.AsyncClient(
                transport=httpx.ASGITransport(
                    app=main.app, client=(f"203.0.113.{i}", 5000)
                ),
                base_url="http://t",
            )
            for i in range(MAX_LIVE_STREAMS + 1)
        ]
        try:
            made = await clients[0].post(
                "/matches", json={"story": "late_comeback", "seed": 1}
            )
            url = f"/matches/{made.json()['match_id']}/stream"
            holders = [
                asyncio.create_task(c.get(url)) for c in clients[:MAX_LIVE_STREAMS]
            ]
            while sum(main._streams.values()) < MAX_LIVE_STREAMS:
                await asyncio.sleep(0.01)
            fourth = await clients[-1].get(url)
            release.set()
            return [fourth, *await asyncio.gather(*holders)]
        finally:
            release.set()
            for c in clients:
                await c.aclose()

    fourth, *held_ok = asyncio.run(scenario())
    assert fourth.status_code == 503
    assert fourth.headers["Retry-After"] == "30"
    assert fourth.json() == {"fallback": "cached"}
    assert [r.status_code for r in held_ok] == [200] * MAX_LIVE_STREAMS


def test_mid_match_the_store_holds_only_what_is_computed_so_far() -> None:
    brief = make_brief(DEFAULT_HOME, DEFAULT_AWAY, "red_card_flip", 3)
    store = InMemoryMatchStore()
    halfway = 2700.0

    async def scenario() -> None:
        stream = run_live(brief, SPEED_FASTEST, pacer=NoPacer(), store=store)
        now = 0.0
        async for msg in stream:
            if msg.type.value == "event" and msg.t.root >= halfway:
                now = msg.t.root
                break
        # The worker runs on; give it until it is ahead of playback, then it waits at the lookahead.
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if max(e.t.root for e in store.events(brief.match_id)) > now:
                break
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.2)
        args = {"match_id": brief.match_id, "t_from": now - 60, "t_to": 99_999}
        async with create_connected_server_and_client_session(
            build_server(store, writable=False)._mcp_server
        ) as public:
            seen = await public.call_tool("get_events", args)
            seen_times = [e["t"] for e in (seen.structuredContent or {})["events"]]
            assert (
                seen_times and max(seen_times) <= now
            )  # the public server has no lookahead
        async with create_connected_server_and_client_session(
            build_server(store, writable=True)._mcp_server
        ) as session:
            got = await session.call_tool("get_events", args)
            times = [e["t"] for e in (got.structuredContent or {})["events"]]
            assert times and now < max(times) <= now + LOOKAHEAD_S
            listed = await session.call_tool("list_beats", {"match_id": brief.match_id})
            partial = (listed.structuredContent or {})["beats"]
        assert all(b["t_detect"] <= now + LOOKAHEAD_S for b in partial)
        async for _ in stream:  # play out the rest
            pass
        final = [b.id.root for b in store.beats(brief.match_id)]
        partial_ids = [b["id"] for b in partial]
        assert partial_ids == final[: len(partial_ids)]
        assert len(partial_ids) < len(final)

    asyncio.run(scenario())


def test_get_and_delete_on_mcp_return_405_at_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MCP_ALLOWED_HOSTS", "testserver")
    with TestClient(main.app) as client:
        for method in ("GET", "DELETE"):
            started = time.monotonic()
            resp = client.request(method, "/mcp", headers=MCP_HEADERS)
            assert resp.status_code == 405
            assert resp.headers["Allow"] == "POST"
            assert time.monotonic() - started < 1.0
