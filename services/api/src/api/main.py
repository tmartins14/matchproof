import asyncio
import gc
import hashlib
from collections import Counter, OrderedDict
from collections.abc import AsyncGenerator, AsyncIterator, Callable
from functools import lru_cache
from importlib.metadata import version
from typing import Annotated, Any

from agents.llm_client import LlmClient, LlmError, from_env
from contracts.models import Fact, MatchBrief, StreamMessage
from fastapi import Body, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from intel.beats import detect_all
from intel.engine import extract_all
from intel.registry import FactRegistry
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from pydantic import ValidationError
from sim import generate
from sim.brief import DEFAULT_AWAY, DEFAULT_HOME, STORYLINES, make_brief
from sim.positions import iter_frames, iter_freeze_frames
from starlette.background import BackgroundTask

from api.live import (
    HEARTBEAT_S,
    SPEED_FAST,
    SPEEDS,
    Pacer,
    RealPacer,
    roster_of,
    run_live,
)
from api.telemetry import configure_telemetry

MODEL_CHECK_PROMPT = "Reply with the single word: ready"
MODEL_CHECK_TIMEOUT_S = 15.0
MAX_STREAMS_PER_CLIENT = 2  # concurrent streams one client address may hold open
MAX_BRIEFS = 200  # briefs kept in memory; the oldest goes first
MAX_CACHED_REGISTRIES = 4  # full fact registries kept for fact lookups
HEARTBEAT_LINE = (
    ": keep-alive\n\n"  # an SSE comment: ignored by the browser, keeps proxies open
)

configure_telemetry()

app = FastAPI(title="Matchproof API")
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
        registry = extract_all(events, frames, freeze, roster_of(brief))
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
) -> StreamingResponse:
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

    async def body() -> AsyncIterator[str]:
        try:
            async for chunk in sse_with_heartbeat(
                run_live(brief, speed, pacer=make_pacer(), after_seq=after)
            ):
                yield chunk
        finally:
            release()

    return StreamingResponse(
        body(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        background=BackgroundTask(release),
    )
