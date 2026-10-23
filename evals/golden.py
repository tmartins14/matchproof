"""The golden matches, built into an in-memory store the way the live path builds them.

Generation is cached on disk by the intel tests' helper (.cache/matches), so a second run is quick.
"""

import sys
from pathlib import Path

from contracts.models import Event, MatchBrief, PositionFrame
from intel.beats import BeatDetector
from intel.engine import FactEngine
from mcp_match import InMemoryMatchStore
from sim.brief import DEFAULT_AWAY, DEFAULT_HOME, make_brief

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "packages" / "intel" / "tests")
)
from matches import read_stream  # type: ignore[import-not-found]


def roster_of(brief: MatchBrief) -> dict[str, str]:
    """Player id to name, as the live path passes it to the fact engine."""
    return {
        p.id.root: p.name for team in (brief.home, brief.away) for p in team.players
    }


def teams_of(brief: MatchBrief) -> dict[str, str]:
    return {"home": brief.home.name, "away": brief.away.name}


def build_store(
    story: str, seed: int, store: InMemoryMatchStore | None = None
) -> tuple[InMemoryMatchStore, str]:
    """Run one match through the engine and beat detector into a store; returns it and the match id."""
    store = store or InMemoryMatchStore()
    brief = make_brief(DEFAULT_HOME, DEFAULT_AWAY, story, seed)
    engine, detector = FactEngine(roster_of(brief), teams_of(brief)), BeatDetector()
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
    return store, brief.match_id
