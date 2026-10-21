"""Generated matches shared by the intel tests, built once per process."""

import gc
from dataclasses import dataclass, field
from functools import cache

from contracts.models import Event, PositionFrame
from sim import generate
from sim.brief import DEFAULT_AWAY, DEFAULT_HOME, make_brief
from sim.positions import run


@dataclass
class Match:
    events: list[Event]
    frames: list[PositionFrame] = field(default_factory=list)
    freeze: list[PositionFrame] = field(default_factory=list)
    stream: list[Event | PositionFrame] = field(default_factory=list)


@cache
def match(story: str, seed: int) -> Match:
    brief = make_brief(DEFAULT_HOME, DEFAULT_AWAY, story, seed)
    # Holding every frame as a model object makes the cyclic collector crawl; pause it while building.
    gc.disable()
    try:
        m = Match(generate(brief))
        for kind, event, frame in run(brief, m.events):
            if kind == "event" and event is not None:
                m.stream.append(event)
            elif frame is not None:
                (m.frames if kind == "frame" else m.freeze).append(frame)
                m.stream.append(frame)
    finally:
        gc.enable()
    gc.freeze()
    return m
