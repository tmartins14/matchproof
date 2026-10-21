"""Generated matches shared by the intel tests.

Two ways in, by what a test needs:
- match() holds every 5 Hz frame and freeze frame as model objects, for the tests that compare the
  streaming and batch paths. Two are kept at most; each is large.
- lean() runs the match straight through the fact engine and beat detector as it is generated and
  keeps only the events, beats and registry. Use it for everything that does not need the frames.
"""

import gc
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import lru_cache

from contracts.models import Beat, Event, PositionFrame
from intel.beats import BeatDetector, merge_stream
from intel.engine import FactEngine
from intel.registry import FactRegistry
from sim import generate
from sim.brief import DEFAULT_AWAY, DEFAULT_HOME, make_brief
from sim.positions import run

KEPT_MATCHES = 2  # matches held at once; the rest are rebuilt on demand


@contextmanager
def gc_paused() -> Iterator[None]:
    """Holding tens of thousands of frame models makes the cyclic collector crawl; pause it."""
    gc.disable()
    try:
        yield
    finally:
        gc.enable()


@dataclass
class Match:
    events: list[Event]
    frames: list[PositionFrame] = field(default_factory=list)
    freeze: list[PositionFrame] = field(default_factory=list)

    @property
    def stream(self) -> list[Event | PositionFrame]:
        """Events, freeze frames and frames in the order the generator yields them."""
        return merge_stream(self.events, self.frames, self.freeze)


@lru_cache(maxsize=KEPT_MATCHES)
def match(story: str, seed: int) -> Match:
    brief = make_brief(DEFAULT_HOME, DEFAULT_AWAY, story, seed)
    with gc_paused():
        m = Match(generate(brief))
        for kind, _, frame in run(brief, m.events):
            if frame is not None:
                (m.frames if kind == "frame" else m.freeze).append(frame)
    return m


@dataclass
class Lean:
    events: list[Event]
    beats: list[Beat]
    registry: FactRegistry


def compute_lean(story: str, seed: int) -> Lean:
    """The live path, minus the wire: no frame is kept once the engine and detector have seen it."""
    brief = make_brief(DEFAULT_HOME, DEFAULT_AWAY, story, seed)
    events = generate(brief)
    engine, detector = FactEngine(), BeatDetector()
    beats: list[Beat] = []
    with gc_paused():
        for kind, event, frame in run(brief, events):
            item = event if kind == "event" else frame
            if item is not None:
                engine.push(item)
                beats += detector.push(item, engine.registry)
        engine.finish()
        beats += detector.finish(engine.registry)
    return Lean(events, beats, engine.registry)


@lru_cache(maxsize=KEPT_MATCHES)
def lean(story: str, seed: int) -> Lean:
    return compute_lean(story, seed)
