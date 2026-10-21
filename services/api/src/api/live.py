"""The live feed: condensed playback of a match, built ahead of the viewer and paced against a clock.

A worker thread runs the generator, fact engine and beat detector LOOKAHEAD_S match seconds ahead of
playback, so a beat is known before the viewer reaches it and nothing heavy runs on the event loop.
The player then lays the entries out on a timeline:

- cruise at `speed` match minutes per real second, frames thinned to WIRE_FPS per real second;
- a focus window around each single-moment beat (FOCUS_BEFORE_S before to FOCUS_AFTER_S after its
  anchor), at FOCUS_SPEED match seconds per real second with every 5 Hz frame;
- at each anchor, its freeze frame and a FREEZE_HOLD_S pause, then the beat.

What is sent, and in what order, is decided by match time and the beats alone; only the waiting
depends on a clock. The same brief and speed always give the same messages with the same seq, which
is what lets a reconnect regenerate the match and carry on after Last-Event-ID.

Sent: every event, frames as above, window facts when their window closes, and each beat with the
facts it cites just before it. The rest of the registry stays server-side, looked up by id.
"""

import asyncio
import threading
import time
from collections import deque
from collections.abc import AsyncGenerator, Callable, Iterator
from dataclasses import dataclass
from typing import Any, Protocol

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
SPEED_FASTEST = 6  # fastest cruise
SPEEDS = (SPEED_REAL_TIME, SPEED_FAST, SPEED_FASTEST)
WIRE_FPS = 10  # most frame messages per real second while cruising
LOOKAHEAD_S = 120.0  # match seconds the pipeline runs ahead of playback
FOCUS_BEFORE_S = 15.0  # a focus window opens this many match seconds before its anchor
FOCUS_AFTER_S = 5.0  # ...and closes this many after
FOCUS_SPEED = (
    1.0  # match seconds per real second inside a focus window; every 5 Hz frame is sent
)
FREEZE_HOLD_S = 6.0  # real seconds held on an anchor's freeze frame
FOCUS_KINDS = frozenset(
    {
        "counter_goal",
        "set_piece_goal",
        "high_turnover_goal",
        "open_play_goal",
        "high_turnover_chance",
        "big_chance",
        "card",
    }
)  # beats with one anchor moment; span beats (spells, follow-ups) get no focus window
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


@dataclass(frozen=True)
class Entry:
    """One thing the pipeline produced, before the player decides whether and when to send it."""

    t: float
    kind: str  # status, event, frame, freeze, fact or beat
    data: Any
    anchor_id: str | None = None  # freeze: the event the frame belongs to


def pipeline(brief: MatchBrief) -> Iterator[list[Entry]]:
    """The match through the engine and detector: the entries each generator item gives rise to."""
    engine = FactEngine(roster_of(brief))
    detector = BeatDetector()
    sent: set[str] = set()
    clock = 0.0

    def entry(t: float, kind: str, data: Any, anchor_id: str | None = None) -> Entry:
        nonlocal clock
        clock = max(clock, t)
        return Entry(clock, kind, data, anchor_id)

    def beat_entries(beat: Beat) -> list[Entry]:
        out: list[Entry] = []
        for fid in beat.fact_ids:
            fact = engine.registry.get(fid.root)
            if fact.id.root not in sent:
                sent.add(fact.id.root)
                out.append(entry(beat.t_detect.root, "fact", fact))
        out.append(entry(beat.t_detect.root, "beat", beat))
        return out

    def window_entries(facts: list[Fact], t: float) -> list[Entry]:
        out: list[Entry] = []
        for f in facts:
            if is_window_fact(f) and f.id.root not in sent:
                sent.add(f.id.root)
                out.append(entry(t, "fact", f))
        return out

    yield [
        entry(0.0, "status", {"state": "pre_match", "message": PRE_MATCH_TEXT}),
        entry(0.0, "status", {"state": "live"}),
    ]
    for kind, event, frame in run(brief, iter_events(brief)):
        item: Event | PositionFrame | None = event if kind == "event" else frame
        if item is None:
            continue
        t = item.t.root
        facts = engine.push(item)
        beats = detector.push(item, engine.registry)
        out = window_entries(facts, t)
        if kind == "event" and event is not None:
            out.append(entry(t, "event", event))
        elif kind == "frame":
            out.append(entry(t, "frame", item))
        elif frame is not None and event is not None:
            out.append(entry(t, "freeze", frame, event.id.root))
        for b in beats:
            out += beat_entries(b)
        if kind == "event" and event is not None:
            if event.type.value == "period_end":
                state = "half_time" if event.period.value == 1 else "full_time"
                text = HALF_TIME_TEXT if event.period.value == 1 else FULL_TIME_TEXT
                out.append(entry(t, "status", {"state": state, "message": text}))
            elif event.type.value == "period_start" and event.period.value == 2:
                out.append(entry(t, "status", {"state": "live"}))
        yield out
    last = [e for f in engine.finish() for e in window_entries([f], clock)]
    for b in detector.finish(engine.registry):
        last += beat_entries(b)
    if last:
        yield last


class _Control:
    """Keeps the worker within LOOKAHEAD_S of playback and lets the player stop it."""

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._playback = 0.0
        self._cancelled = False

    def advance(self, t: float) -> None:
        with self._cond:
            self._playback = max(self._playback, t)
            self._cond.notify_all()

    def cancel(self) -> None:
        with self._cond:
            self._cancelled = True
            self._cond.notify_all()

    def wait_until_allowed(self, t: float) -> bool:
        """Block until t is within the lookahead; False if the stream was cancelled meanwhile."""
        with self._cond:
            while not self._cancelled and t > self._playback + LOOKAHEAD_S:
                self._cond.wait()
            return not self._cancelled


Posted = list[Entry] | Exception | None


def _post(
    loop: asyncio.AbstractEventLoop, queue: "asyncio.Queue[Posted]", item: Posted
) -> bool:
    try:
        loop.call_soon_threadsafe(queue.put_nowait, item)
    except RuntimeError:  # the loop closed: nobody is listening
        return False
    return True


def _produce(
    brief: MatchBrief,
    loop: asyncio.AbstractEventLoop,
    queue: "asyncio.Queue[Posted]",
    control: _Control,
) -> None:
    """Thread body: feed the pipeline's entries to the player, never too far ahead of it."""
    try:
        for batch in pipeline(brief):
            if not batch:
                continue
            if not control.wait_until_allowed(batch[0].t):
                return
            if not _post(loop, queue, batch):
                return
    except Exception as exc:  # noqa: BLE001 - crosses the thread boundary; the player re-raises it
        _post(loop, queue, exc)
        return
    _post(loop, queue, None)


class _Feed:
    """The entries as they arrive, held until the player can see FOCUS_BEFORE_S past the next one."""

    def __init__(self, queue: "asyncio.Queue[Posted]") -> None:
        self._queue = queue
        self._buffer: deque[Entry] = deque()
        self._last = -1.0
        self._done = False
        self.anchor_times: list[float] = []
        self.anchor_ids: set[str] = set()

    def _register(self, e: Entry) -> None:
        if e.kind == "beat" and e.data.kind.value in FOCUS_KINDS:
            self.anchor_times.append(e.data.t_from.root)
            self.anchor_ids.add(e.data.anchor_event_id.root)

    async def next(self) -> Entry | None:
        # Strictly past the window lead: a beat is detected at its anchor, so every beat whose window
        # could already have opened is in the buffer by then.
        while not self._done and (
            not self._buffer or self._last <= self._buffer[0].t + FOCUS_BEFORE_S
        ):
            got = await self._queue.get()
            if got is None:
                self._done = True
            elif isinstance(got, Exception):
                raise got
            else:
                for e in got:
                    self._register(e)
                    self._buffer.append(e)
                    self._last = e.t
        return self._buffer.popleft() if self._buffer else None


class _Builder:
    """Numbers messages and keeps their match clock from running backwards."""

    def __init__(self, speed: int) -> None:
        self.speed = speed
        self._seq = 0
        self._t = 0.0

    def message(self, kind: str, t: float, data: object) -> StreamMessage:
        self._t = max(self._t, t)
        msg = StreamMessage.model_validate(
            {"seq": self._seq, "type": kind, "t": self._t, "data": data}
        )
        self._seq += 1
        return msg

    def status(
        self,
        state: str,
        t: float,
        *,
        text: str | None = None,
        event_id: str | None = None,
    ) -> StreamMessage:
        data: dict[str, object] = {"state": state}
        if state not in ("focus", "freeze"):
            data["speed"] = self.speed
        if event_id is not None:
            data["event_id"] = event_id
        if text is not None:
            data["message"] = text
        return self.message("status", t, data)


def merge_windows(anchor_times: list[float]) -> list[tuple[float, float]]:
    """Focus windows around the anchors, overlapping ones merged."""
    out: list[tuple[float, float]] = []
    for a in sorted(anchor_times):
        start, end = max(a - FOCUS_BEFORE_S, 0.0), a + FOCUS_AFTER_S
        if out and start <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], end))
        else:
            out.append((start, end))
    return out


class _Timeline:
    """Where playback is, in match seconds and real seconds from the start."""

    def __init__(self, speed: int, feed: _Feed, builder: _Builder) -> None:
        self.cruise_rate = speed * SECONDS_PER_MINUTE
        self.cur_t = 0.0
        self.real = 0.0
        self.focus = False
        self._feed = feed
        self._builder = builder

    def _move(self, to: float, rate: float) -> None:
        if to > self.cur_t:
            self.real += (to - self.cur_t) / rate
            self.cur_t = to

    def advance(self, t: float) -> Iterator[tuple[float, StreamMessage]]:
        """Move to match time t, announcing each focus window entered and left on the way."""
        while True:
            windows = merge_windows(self._feed.anchor_times)
            if not self.focus:
                ahead = next(
                    (w for w in windows if w[1] > self.cur_t and w[0] <= t), None
                )
                if ahead is None:
                    self._move(t, self.cruise_rate)
                    return
                start = max(ahead[0], self.cur_t)
                self._move(start, self.cruise_rate)
                self.focus = True
                yield self.real, self._builder.status("focus", start)
            else:
                end = next(
                    (w[1] for w in windows if w[0] <= self.cur_t <= w[1]), self.cur_t
                )
                if t <= end:
                    self._move(t, FOCUS_SPEED)
                    return
                self._move(end, FOCUS_SPEED)
                self.focus = False
                yield self.real, self._builder.status("live", end)

    def hold(self, real_s: float) -> None:
        self.real += real_s


async def schedule(
    feed: _Feed, speed: int, control: _Control
) -> AsyncGenerator[tuple[float, StreamMessage], None]:
    """Messages with the real second (from the start) each is due, in order."""
    builder = _Builder(speed)
    timeline = _Timeline(speed, feed, builder)
    frame_gap = speed * SECONDS_PER_MINUTE / WIRE_FPS + FRAME_GUARD_S
    next_frame_t = 0.0
    while (e := await feed.next()) is not None:
        control.advance(e.t)
        for due in timeline.advance(e.t):
            yield due
        due_s = timeline.real
        if e.kind == "status":
            yield (
                due_s,
                builder.status(e.data["state"], e.t, text=e.data.get("message")),
            )
        elif e.kind == "frame":
            if timeline.focus or e.t >= next_frame_t:
                if not timeline.focus:
                    next_frame_t = e.t + frame_gap
                yield due_s, builder.message("frame", e.t, e.data)
        elif e.kind == "freeze":
            if e.anchor_id in feed.anchor_ids:
                yield due_s, builder.status("freeze", e.t, event_id=e.anchor_id)
                yield due_s, builder.message("frame", e.t, e.data)
                timeline.hold(FREEZE_HOLD_S)
        else:  # event, fact, beat
            yield due_s, builder.message(e.kind, e.t, e.data)


async def run_live(
    brief: MatchBrief,
    speed: int = SPEED_FAST,
    *,
    pacer: Pacer | None = None,
    after_seq: int = -1,
) -> AsyncGenerator[StreamMessage, None]:
    """The match as stream messages, each sent when its turn on the timeline comes.

    `after_seq` skips every message up to and including that seq without waiting; the clock then
    starts from the first message that is sent. Resume with the same `speed`: it decides which frames
    are thinned, so it decides the numbering.
    """
    if speed not in SPEEDS:
        raise ValueError(f"speed must be one of {SPEEDS}, not {speed}")
    pacer = pacer or RealPacer()
    queue: asyncio.Queue[Posted] = asyncio.Queue()
    control = _Control()
    worker = threading.Thread(
        target=_produce,
        args=(brief, asyncio.get_running_loop(), queue, control),
        name=f"pipeline-{brief.match_id}",
        daemon=True,
    )
    worker.start()
    plan = schedule(_Feed(queue), speed, control)
    origin: float | None = None
    try:
        async for due, msg in plan:
            if msg.seq <= after_seq:
                continue
            if origin is None:
                origin = pacer.now() - due
            await pacer.sleep_until(origin + due)
            yield msg
    finally:
        control.cancel()
        await plan.aclose()
