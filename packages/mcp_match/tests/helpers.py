"""A finished match in a store, and a client for the in-memory server."""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path
from typing import Any

from contracts.models import Event, PositionFrame
from intel.beats import BeatDetector
from intel.engine import FactEngine
from jsonschema import Draft202012Validator
from matches import read_stream
from mcp import ClientSession
from mcp.shared.memory import create_connected_server_and_client_session
from mcp_match import InMemoryMatchStore, MatchStore, build_server
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012
from sim.brief import DEFAULT_AWAY, DEFAULT_HOME, make_brief

ROOT = Path(__file__).resolve().parents[3]


def fill(store: MatchStore, story: str, seed: int) -> str:
    """Run a match through the engine and detector into `store`; returns its match id."""
    brief = make_brief(DEFAULT_HOME, DEFAULT_AWAY, story, seed)
    engine, detector = FactEngine(), BeatDetector()
    store.begin(brief, engine.registry)
    for _, item in read_stream(brief):
        if isinstance(item, Event):
            store.add_event(brief.match_id, item)
        elif isinstance(item, PositionFrame) and item.freeze_frame_of is not None:
            store.add_freeze_frame(brief.match_id, item.freeze_frame_of.root, item)
        engine.push(item)
        for beat in detector.push(item, engine.registry):
            store.add_beat(brief.match_id, beat)
    engine.finish()
    for beat in detector.finish(engine.registry):
        store.add_beat(brief.match_id, beat)
    store.finish(brief.match_id)
    return brief.match_id


@lru_cache(maxsize=1)
def finished() -> tuple[InMemoryMatchStore, str]:
    store = InMemoryMatchStore()
    return store, fill(store, "red_card_flip", 3)


@asynccontextmanager
async def client_for(store: MatchStore, writable: bool) -> AsyncIterator[ClientSession]:
    async with create_connected_server_and_client_session(
        build_server(store, writable)._mcp_server
    ) as session:
        yield session


async def call(session: ClientSession, tool: str, **args: Any) -> dict[str, Any]:
    """The structured result of a tool call that must succeed."""
    result = await session.call_tool(tool, args)
    assert not result.isError, result.content
    assert result.structuredContent is not None
    return result.structuredContent


def validator(schema: str) -> Draft202012Validator:
    schemas = {
        p.name: json.loads(p.read_text())
        for p in (ROOT / "schemas").glob("*.schema.json")
    }
    registry: Registry[Any] = Registry()
    for s in schemas.values():
        registry = registry.with_resource(
            str(s["$id"]), Resource.from_contents(s, DRAFT202012)
        )
    return Draft202012Validator(schemas[f"{schema}.schema.json"], registry=registry)
