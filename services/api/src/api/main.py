import asyncio
import gc
import hashlib
import os
from collections import Counter, OrderedDict
from collections.abc import AsyncGenerator, AsyncIterator, Callable
from contextlib import asynccontextmanager
from functools import lru_cache
from importlib.metadata import version
from typing import Annotated, Any

from agents.budget import budget
from agents.llm_client import LlmClient, LlmError, client_for, from_env
from contracts.models import Fact, MatchBrief, StreamMessage
from fastapi import Body, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from intel.beats import detect_all
from intel.engine import extract_all
from intel.registry import FactRegistry
from mcp import ClientSession
from mcp.shared.memory import create_connected_server_and_client_session
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from pydantic import ValidationError
from sim import generate
from sim.brief import DEFAULT_AWAY, DEFAULT_HOME, STORYLINES, make_brief
from sim.positions import iter_frames, iter_freeze_frames
from starlette.background import BackgroundTask
from starlette.routing import Route

from api.agents_runtime import AgentRuntime, DownRun, MatchRun, SessionServer
from api.live import (
    HEARTBEAT_S,
    MAX_LIVE_STREAMS,
    SPEED_FAST,
    SPEEDS,
    Pacer,
    RealPacer,
    roster_of,
    run_live,
    teams_of,
)
from api.matchdata import PublicMcp, get_internal_server, store
from api.telemetry import configure_telemetry

MODEL_CHECK_PROMPT = "Reply with the single word: ready"
MODEL_CHECK_TIMEOUT_S = 15.0
RETRY_AFTER_S = (
    30  # what a client is told to wait when the replica is at MAX_LIVE_STREAMS
)
MAX_STREAMS_PER_CLIENT = 2  # concurrent streams one client address may hold open
MAX_BRIEFS = 200  # briefs kept in memory; the oldest goes first
MAX_CACHED_REGISTRIES = 4  # full fact registries kept for fact lookups
HEARTBEAT_LINE = (
    ": keep-alive\n\n"  # an SSE comment: ignored by the browser, keeps proxies open
)

configure_telemetry()

public_mcp = PublicMcp()
agent_runtime: AgentRuntime | None = (
    None  # the agent workflow, once the lifespan has built it
)
agents_configured = (
    False  # models are configured; if the runtime is missing, it failed to start
)


def build_agent_runtime(session: ClientSession) -> AgentRuntime:
    """The workflow's runtime over an in-process session to the internal MCP server."""
    return AgentRuntime(
        SessionServer(session),
        narrator=client_for("narrator"),
        judge=client_for("judge"),
        producer=client_for("producer"),
        auditor=client_for("auditor"),
    )


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    global agent_runtime, agents_configured
    server = public_mcp.start(store)
    async with server.session_manager.run():
        agents_configured = bool(os.environ.get("MODEL_BASE_URL"))
        if not agents_configured:
            yield
            return
        # The internal server (with put_claims and put_audit) is reached in process, over a memory
        # transport. It is never mounted and nothing listens for it (ADR 0008).
        internal = get_internal_server(store)
        async with create_connected_server_and_client_session(
            internal._mcp_server
        ) as session:
            try:
                agent_runtime = build_agent_runtime(session)
            except LlmError:
                agent_runtime = None
            try:
                yield
            finally:
                agent_runtime = None


app = FastAPI(title="Matchproof API", lifespan=lifespan)
app.router.routes.append(Route("/mcp", endpoint=public_mcp))
FastAPIInstrumentor.instrument_app(app)


@lru_cache(maxsize=1)
def get_llm_client() -> LlmClient:
    return from_env()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": version("matchproof-api")}


@app.get("/health/model", response_model=None)
def health_model() -> dict[str, str | int] | JSONResponse:
    try:
        reply = get_llm_client().complete(MODEL_CHECK_PROMPT)
    except LlmError as exc:
        return JSONResponse(
            status_code=503, content={"status": "error", "error": exc.cause_name}
        )
    return {
        "status": "ok",
        "model": reply.model,
        "reply": reply.text,
        "latency_ms": reply.latency_ms,
    }


@app.get("/health/budget")
def health_budget() -> dict[str, Any]:
    """Tokens used today against DAILY_TOKEN_CAP, by agent."""
    return budget.snapshot()


# ---- matches ---------------------------------------------------------------------------------
_briefs: OrderedDict[str, MatchBrief] = OrderedDict()
_streams: Counter[str] = Counter()
make_pacer: Callable[[], Pacer] = RealPacer  # tests swap this for a no-op clock


def store_brief(brief: MatchBrief) -> str:
    """Keep a brief and return its match id. A different brief under a taken id gets a hash suffix."""
    match_id = brief.match_id
    held = _briefs.get(match_id)
    if held is not None and held != brief:
        digest = hashlib.sha256(brief.model_dump_json().encode()).hexdigest()[:8]
        match_id = f"{match_id}-{digest}"
        brief = brief.model_copy(update={"match_id": match_id})
    _briefs[match_id] = brief
    _briefs.move_to_end(match_id)
    while len(_briefs) > MAX_BRIEFS:
        _briefs.popitem(last=False)
    return match_id


def brief_of(match_id: str) -> MatchBrief:
    brief = _briefs.get(match_id)
    if brief is None:
        raise HTTPException(status_code=404, detail=f"unknown match {match_id}")
    return brief


@app.post("/matches")
def create_match(body: Annotated[dict[str, Any], Body()]) -> dict[str, str]:
    """Take a MatchBrief, or {story, seed} for the default tactics, and return {match_id}."""
    try:
        if "story" in body:
            story = body["story"]
            if story not in STORYLINES:
                raise HTTPException(status_code=422, detail=f"unknown story {story!r}")
            seed = body.get("seed", 0)
            if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
                raise HTTPException(
                    status_code=422, detail="seed must be a non-negative integer"
                )
            brief = make_brief(DEFAULT_HOME, DEFAULT_AWAY, story, seed)
        else:
            brief = MatchBrief.model_validate(body)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422, detail=exc.errors(include_url=False, include_context=False)
        ) from exc
    return {"match_id": store_brief(brief)}


@lru_cache(maxsize=MAX_CACHED_REGISTRIES)
def match_registry(match_id: str) -> FactRegistry:
    """Every fact of a match, on-demand beat facts included, for lookups by id."""
    brief = brief_of(match_id)
    events = generate(brief)
    gc.disable()  # tens of thousands of frame models; the cyclic collector would crawl over them
    try:
        frames = list(iter_frames(brief, events))
        freeze = list(iter_freeze_frames(brief, events))
        registry = extract_all(
            events, frames, freeze, roster_of(brief), teams_of(brief)
        )
        detect_all(events, frames, freeze, registry)
    finally:
        gc.enable()
    return registry


@app.get("/matches/{match_id}/facts/{fact_id}")
def get_fact(match_id: str, fact_id: str) -> dict[str, Any]:
    brief_of(match_id)
    try:
        fact: Fact = match_registry(match_id).get(fact_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown fact {fact_id}") from exc
    out: dict[str, Any] = fact.model_dump(mode="json", by_alias=True, exclude_none=True)
    return out


def run_of(match_id: str) -> MatchRun:
    brief_of(match_id)
    run = agent_runtime.existing(match_id) if agent_runtime is not None else None
    if run is None:
        raise HTTPException(status_code=404, detail=f"no agent run for {match_id}")
    return run


@app.get("/matches/{match_id}/audit")
def get_audit(match_id: str) -> dict[str, Any]:
    """The second model's check of this match's claims: how many, how often it agreed, and why not."""
    return run_of(match_id).audit_summary()


@app.get("/matches/{match_id}/producer-log")
def get_producer_log(match_id: str) -> list[dict[str, Any]]:
    """Which beats the Producer put on the feed and which it left off, with a line each."""
    return run_of(match_id).producer_log()


def sse(msg: StreamMessage) -> str:
    body = msg.model_dump_json(by_alias=True, exclude_none=True)
    return f"id: {msg.seq}\nevent: {msg.type.value}\ndata: {body}\n\n"


async def sse_with_heartbeat(
    messages: AsyncGenerator[StreamMessage, None],
) -> AsyncIterator[str]:
    """SSE text for each message, plus a comment line whenever HEARTBEAT_S passes without one."""
    pending: asyncio.Task[StreamMessage] | None = None
    try:
        while True:
            if pending is None:
                pending = asyncio.ensure_future(anext(messages))
            done, _ = await asyncio.wait({pending}, timeout=HEARTBEAT_S)
            if not done:
                yield HEARTBEAT_LINE
                continue
            task, pending = pending, None
            try:
                msg = task.result()
            except StopAsyncIteration:
                return
            yield sse(msg)
    finally:
        if pending is not None:
            pending.cancel()
        await messages.aclose()


@app.get("/matches/{match_id}/stream")
async def stream_match(
    request: Request,
    match_id: str,
    speed: Annotated[int, Query()] = SPEED_FAST,
    last_event_id: Annotated[str | None, Header()] = None,
) -> Response:
    brief = brief_of(match_id)
    if speed not in SPEEDS:
        raise HTTPException(
            status_code=422, detail=f"speed must be one of {list(SPEEDS)}"
        )
    after = -1
    if last_event_id is not None:
        try:
            after = int(last_event_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail="Last-Event-ID must be a seq number"
            ) from exc
    if sum(_streams.values()) >= MAX_LIVE_STREAMS:
        return JSONResponse(
            status_code=503,
            content={"fallback": "cached"},
            headers={"Retry-After": str(RETRY_AFTER_S)},
        )
    client = request.client.host if request.client else "unknown"
    if _streams[client] >= MAX_STREAMS_PER_CLIENT:
        raise HTTPException(status_code=429, detail="too many open streams")
    _streams[client] += 1
    released = False

    def release() -> None:
        nonlocal released
        if not released:
            released = True
            _streams[client] -= 1

    agents: MatchRun | DownRun | None = None
    if agent_runtime is not None:
        agents = agent_runtime.match(brief)
    elif agents_configured:
        agents = DownRun()  # models are configured but the workflow did not start

    async def body() -> AsyncIterator[str]:
        try:
            async for chunk in sse_with_heartbeat(
                run_live(
                    brief,
                    speed,
                    pacer=make_pacer(),
                    after_seq=after,
                    store=store,
                    agents=agents,
                )
            ):
                yield chunk
        finally:
            if agents is not None:
                agents.close()  # ends the match's root span; a reconnect's spans still nest under it
            release()

    return StreamingResponse(
        body(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        background=BackgroundTask(release),
    )
