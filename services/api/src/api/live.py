"""The live feed: a match walked through the fact engine and beat detector, paced against a clock.

run_live() is an async generator of StreamMessage. Everything about *what* is sent is decided by match
time alone (frame thinning included), so the same brief and speed always give the same messages with
the same seq; only the waiting depends on a clock. That is what lets a reconnect regenerate the match
and carry on after Last-Event-ID.

What goes out: every event, frames thinned to WIRE_FPS per real second, window facts when their window
closes, and each beat with the facts it cites just before it. Freeze frames and the rest of the
registry stay server-side and are looked up by id.
"""

import asyncio
import time
from collections.abc import AsyncGenerator, Callable, Iterator
from typing import Protocol

from contracts.models import (
    Beat,
    Event,
    Fact,
    MatchBrief,
    PositionFrame,
    StreamMessage,
)
from intel.beats import BeatDetector
from intel.engine import FactEngine
from sim import iter_events
from sim.positions import run

SPEED_REAL_TIME = 1  # match minutes per real second: slowest
SPEED_FAST = 3  # the default
SPEED_FASTEST = 6  # a whole match in about 16 real seconds
SPEEDS = (SPEED_REAL_TIME, SPEED_FAST, SPEED_FASTEST)
WIRE_FPS = 10  # most frame messages per real second, whatever the speed
SECONDS_PER_MINUTE = 60.0
HEARTBEAT_S = 15.0  # real seconds of silence before the SSE layer sends a comment line
FRAME_GUARD_S = (
    1e-6  # keeps float error from putting an eleventh frame in one real second
)
PRE_MATCH_TEXT = "Teams are out."
HALF_TIME_TEXT = "Half-time."
FULL_TIME_TEXT = "Full-time."


class Pacer(Protocol):
    """The clock that decides how long to wait; swapped for a fake or a no-op in tests."""

    def now(self) -> float: ...

    async def sleep_until(self, real_t: float) -> None: ...


class RealPacer:
    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._clock = clock

    def now(self) -> float:
        return self._clock()

    async def sleep_until(self, real_t: float) -> None:
        # sleep(0) at least hands the loop back, so other streams are served between messages.
        await asyncio.sleep(max(real_t - self._clock(), 0.0))


class NoPacer:
    """Pacing off: nothing waits."""

    def now(self) -> float:
        return 0.0

    async def sleep_until(self, real_t: float) -> None:
        return None


def roster_of(brief: MatchBrief) -> dict[str, str]:
    return {
        p.id.root: p.name for team in (brief.home, brief.away) for p in team.players
    }


def is_window_fact(f: Fact) -> bool:
    """Window facts cite exactly one window; half and match facts cite several."""
    return len(f.source_ids) == 1 and f.source_ids[0].root.startswith("win-")


class _Messages:
    """Turns the walk through a match into numbered messages. Pure and synchronous."""

    def __init__(self, brief: MatchBrief, speed: int) -> None:
        self.brief = brief
        self.speed = speed
        self.engine = FactEngine(roster_of(brief))
        self.detector = BeatDetector()
        self._seq = 0
        self._t = 0.0
        self._sent_facts: set[str] = set()
        self._frame_gap = speed * SECONDS_PER_MINUTE / WIRE_FPS + FRAME_GUARD_S
        self._next_frame_t = 0.0

    def _message(self, kind: str, t: float, data: object) -> StreamMessage:
        self._t = max(self._t, t)
        msg = StreamMessage.model_validate(
            {"seq": self._seq, "type": kind, "t": self._t, "data": data}
        )
        self._seq += 1
        return msg

    def _status(self, state: str, text: str | None = None) -> StreamMessage:
        data: dict[str, object] = {"state": state, "speed": self.speed}
        if text is not None:
            data["message"] = text
        return self._message("status", self._t, data)

    def _fact(self, fact: Fact, t: float) -> Iterator[StreamMessage]:
        if fact.id.root not in self._sent_facts:
            self._sent_facts.add(fact.id.root)
            yield self._message("fact", t, fact)

    def _beat(self, beat: Beat) -> Iterator[StreamMessage]:
        for fid in beat.fact_ids:
            yield from self._fact(
                self.engine.registry.get(fid.root), beat.t_detect.root
            )
        yield self._message("beat", beat.t_detect.root, beat)

    def walk(self) -> Iterator[StreamMessage]:
        yield self._status("pre_match", PRE_MATCH_TEXT)
        yield self._status("live")
        for kind, event, frame in run(self.brief, iter_events(self.brief)):
            # A freeze frame arrives with its event attached; only the "event" tuple is the event.
            event = event if kind == "event" else None
            item: Event | PositionFrame | None = event or frame
            if item is None:
                continue
            t = item.t.root
            facts = self.engine.push(item)
            beats = self.detector.push(item, self.engine.registry)
            for f in facts:
                if is_window_fact(f):
                    yield from self._fact(f, t)
            if isinstance(event, Event):
                yield self._message("event", t, event)
            elif kind == "frame" and frame is not None and t >= self._next_frame_t:
                self._next_frame_t = t + self._frame_gap
                yield self._message("frame", t, frame)
            for b in beats:
                yield from self._beat(b)
            if isinstance(event, Event) and event.type.value == "period_end":
                if event.period.value == 1:
                    yield self._status("half_time", HALF_TIME_TEXT)
                else:
                    yield self._status("full_time", FULL_TIME_TEXT)
            elif (
                isinstance(event, Event)
                and event.type.value == "period_start"
                and event.period.value == 2
            ):
                yield self._status("live")
        closing = self.engine.finish()
        for f in closing:
            if is_window_fact(f):
                yield from self._fact(f, self._t)
        for b in self.detector.finish(self.engine.registry):
            yield from self._beat(b)


async def run_live(
    brief: MatchBrief,
    speed: int = SPEED_FAST,
    *,
    pacer: Pacer | None = None,
    after_seq: int = -1,
) -> AsyncGenerator[StreamMessage, None]:
    """The match as stream messages, one per `speed` match minutes per real second of waiting.

    `after_seq` skips every message up to and including that seq without waiting; the clock then
    starts from the first message that is sent. Resume with the same `speed`: it decides which frames
    are thinned, so it decides the numbering.
    """
    if speed not in SPEEDS:
        raise ValueError(f"speed must be one of {SPEEDS}, not {speed}")
    pacer = pacer or RealPacer()
    rate = speed * SECONDS_PER_MINUTE
    origin: float | None = None
    for msg in _Messages(brief, speed).walk():
        if msg.seq <= after_seq:
            continue
        due = msg.t.root / rate
        if origin is None:
            origin = pacer.now() - due
        await pacer.sleep_until(origin + due)
        yield msg
