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

While it runs, the worker also writes what it has computed into a MatchStore (when given one), so
agents can query a match mid-stream. It writes a batch only once the batch is within LOOKAHEAD_S of
playback, so the store never holds more than the lookahead.

Sent: every event, frames as above, window facts and the desk's running totals and momentum when
their span closes, and each beat with the facts it cites just before it. Every fact carries its
plain-English `label`, written by intel.labels. The rest of the registry stays server-side, looked up by id.

With a MatchRun (the agent workflow), each beat is also handed to it as the worker finds it, in the
lookahead. When playback reaches the beat, its claims follow it: a claim whose check has finished is
sent with its final verdict; one still being checked is sent as `checking` and gets a `verdict`
message the moment the Checker finishes. That is verify before air. The messages then count in the
order they are sent, so a stream with agents is not reproducible by seq alone; resume after a
Last-Event-ID continues the numbering and reuses the claims already settled.
"""

import asyncio
import json
import threading
import time
from collections import deque
from collections.abc import AsyncGenerator, Callable, Iterator
from dataclasses import dataclass
from typing import Any, Protocol

from contracts.models import (
    Beat,
    Claim,
    Event,
    Fact,
    MatchBrief,
    PositionFrame,
    State,
    Status,
    StreamMessage,
)
from intel.beats import BeatDetector
from intel.desk import highlight_for, is_desk_fact
from intel.engine import FactEngine
from intel.labels import LabelContext, desk_label_for
from intel.score import is_goal, match_score
from mcp_match.store import MatchStore
from sim import iter_events
from sim.positions import run

from api.agents_runtime import DownRun, MatchRun

SPEED_REAL_TIME = 1  # match minutes per real second: slowest
SPEED_FAST = 3  # the default
SPEED_FASTEST = 6  # fastest cruise
SPEEDS = (SPEED_REAL_TIME, SPEED_FAST, SPEED_FASTEST)
MAX_LIVE_STREAMS = (
    3  # streams one replica runs at once; the API answers a further one with 503
)
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
PRODUCER_WAIT_S = 15.0  # real seconds a beat waits at air for the Producer's decision
DRAIN_TIMEOUT_S = (
    60.0  # real seconds after full time the stream waits for checks still running
)
FULL_TIME_HOLD_S = (
    30.0  # real seconds full time waits for audits and corrections still running
)
HOLD_POLL_S = 0.05  # how often the hold looks at the ledger when nothing lands
PAUSED_TEXT = "Narration is paused for today."
UNAVAILABLE_TEXT = "Verification is unavailable right now."


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


def teams_of(brief: MatchBrief) -> dict[str, str]:
    return {"home": brief.home.name, "away": brief.away.name}


def is_window_fact(f: Fact) -> bool:
    """Window facts cite exactly one window; half and match facts cite several."""
    return len(f.source_ids) == 1 and f.source_ids[0].root.startswith("win-")


def is_sent_on_close(f: Fact) -> bool:
    """Facts sent when their span closes, without a beat citing them."""
    return is_window_fact(f) or is_desk_fact(f)


@dataclass(frozen=True)
class Entry:
    """One thing the pipeline produced, before the player decides whether and when to send it."""

    t: float
    kind: str  # status, event, frame, freeze, fact or beat
    data: Any
    anchor_id: str | None = None  # freeze: the event the frame belongs to


def pipeline(
    brief: MatchBrief, engine: FactEngine | None = None, until_s: float | None = None
) -> Iterator[list[Entry]]:
    """The match through the engine and detector: the entries each generator item gives rise to.

    Pass `engine` to keep hold of its registry while the match runs. `until_s` ends the match early
    with a full-time status once play passes that match second; tests use it to play a short match.
    """
    engine = engine or FactEngine(roster_of(brief), teams_of(brief))
    detector = BeatDetector()
    sent: set[str] = set()
    seen: dict[str, Event] = {}
    ctx = LabelContext(teams_of(brief), seen, engine.registry)
    clock = 0.0

    def score_now() -> dict[str, int]:
        home, away = match_score(seen.values())
        return {"home": home, "away": away}

    def entry(t: float, kind: str, data: Any, anchor_id: str | None = None) -> Entry:
        nonlocal clock
        clock = max(clock, t)
        return Entry(clock, kind, data, anchor_id)

    def labelled(fact: Fact) -> Fact:
        return fact.model_copy(update={"label": desk_label_for(fact, ctx)})

    def beat_entries(beat: Beat) -> list[Entry]:
        out: list[Entry] = []
        for fid in beat.fact_ids:
            fact = engine.registry.get(fid.root)
            if fact.id.root not in sent:
                sent.add(fact.id.root)
                out.append(entry(beat.t_detect.root, "fact", labelled(fact)))
        marked = beat.model_copy(
            update={
                "highlight": highlight_for(beat, seen.get(beat.anchor_event_id.root))
            }
        )
        out.append(entry(beat.t_detect.root, "beat", marked))
        return out

    def window_entries(facts: list[Fact], t: float) -> list[Entry]:
        out: list[Entry] = []
        for f in facts:
            if is_sent_on_close(f) and f.id.root not in sent:
                sent.add(f.id.root)
                out.append(entry(t, "fact", labelled(f)))
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
        if until_s is not None and t > until_s:
            yield [
                entry(
                    until_s,
                    "status",
                    {
                        "state": "full_time",
                        "message": FULL_TIME_TEXT,
                        "score": score_now(),
                    },
                )
            ]
            break
        if isinstance(item, Event):
            seen[item.id.root] = item
        facts = engine.push(item)
        beats = detector.push(item, engine.registry)
        out = window_entries(facts, t)
        if kind == "event" and event is not None:
            out.append(entry(t, "event", event))
            if is_goal(event):
                out.append(entry(t, "status", {"state": "score", "score": score_now()}))
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
                status: dict[str, Any] = {"state": state, "message": text}
                if state == "full_time":
                    status["score"] = score_now()
                out.append(entry(t, "status", status))
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


def _publish(store: MatchStore, match_id: str, batch: list[Entry]) -> None:
    """Make a batch visible to the agents' queries."""
    for e in batch:
        if e.kind == "event":
            store.add_event(match_id, e.data)
        elif e.kind == "freeze" and e.anchor_id is not None:
            store.add_freeze_frame(match_id, e.anchor_id, e.data)
        elif e.kind == "beat":
            store.add_beat(match_id, e.data)


def _produce(
    brief: MatchBrief,
    loop: asyncio.AbstractEventLoop,
    queue: "asyncio.Queue[Posted]",
    control: _Control,
    store: MatchStore | None = None,
    on_beat: Callable[[Beat], None] | None = None,
    until_s: float | None = None,
) -> None:
    """Thread body: feed the pipeline's entries to the player, never too far ahead of it.
    `on_beat` is called on the event loop for each beat as it is found."""
    engine = FactEngine(roster_of(brief), teams_of(brief))
    if store is not None:
        store.begin(brief, engine.registry)
    try:
        for batch in pipeline(brief, engine, until_s):
            if not batch:
                continue
            if not control.wait_until_allowed(batch[0].t):
                return
            if store is not None:
                _publish(store, brief.match_id, batch)
            if on_beat is not None:
                for e in batch:
                    if e.kind == "beat":
                        loop.call_soon_threadsafe(on_beat, e.data)
            if not _post(loop, queue, batch):
                return
        if store is not None:
            store.finish(brief.match_id)
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
        score: dict[str, int] | None = None,
    ) -> StreamMessage:
        data: dict[str, object] = {"state": state}
        if state not in ("focus", "freeze"):
            data["speed"] = self.speed
        if event_id is not None:
            data["event_id"] = event_id
        if text is not None:
            data["message"] = text
        if score is not None:
            data["score"] = score
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
                builder.status(
                    e.data["state"],
                    e.t,
                    text=e.data.get("message"),
                    score=e.data.get("score"),
                ),
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


class _AgentTrack:
    """What one stream has sent about the agents: the numbering, and which claims are on screen."""

    def __init__(self, run: MatchRun | DownRun, first_seq: int) -> None:
        self.run = run
        self.seq = first_seq
        self.t = 0.0
        self.aired: dict[str, str | None] = {}  # claim id to the span id of its beat
        self.late: asyncio.Queue[tuple[str, Claim, str | None]] = asyncio.Queue()
        self.followers: set[asyncio.Task[None]] = set()
        self.told_paused = False
        self.told_down = False

    def number(self, msg: StreamMessage) -> StreamMessage:
        self.t = max(self.t, msg.t.root)
        out = msg.model_copy(update={"seq": self.seq})
        self.seq += 1
        return out

    def build(
        self, kind: str, data: dict[str, Any], span_id: str | None = None
    ) -> StreamMessage:
        raw: dict[str, Any] = {"seq": self.seq, "type": kind, "t": self.t, "data": data}
        if span_id is not None:
            raw["span_id"] = span_id
        self.seq += 1
        return StreamMessage.model_validate(raw)

    def notice(self, text: str) -> StreamMessage:
        return self.build("status", {"state": "notice", "message": text})

    def from_late(self, item: tuple[str, Claim, str | None]) -> StreamMessage:
        kind, claim, span_id = item
        return self.build(kind, _claim_data(claim), span_id)

    def drain(self) -> Iterator[StreamMessage]:
        while not self.late.empty():
            yield self.from_late(self.late.get_nowait())

    async def follow(self, beat_id: str) -> None:
        """Queue the beat's claims for sending: as `checking` while the Checker works, then their
        verdicts; at once with their verdicts if the check finished before the beat aired."""
        track = self.run.track(beat_id)
        if track is None:
            return
        if not track.done.done():
            first: set[asyncio.Future[Any]] = {track.drafted, track.done}
            await asyncio.wait(first, return_when=asyncio.FIRST_COMPLETED)
            if track.drafted.done() and not track.done.done():
                for claim in track.drafted.result():
                    self.aired[claim.id.root] = None
                    self.late.put_nowait(("claim", claim, None))
        await asyncio.shield(track.done)
        span_id = self.run.span_id(beat_id)
        for claim in self.run.claims_now(beat_id):
            kind = "verdict" if claim.id.root in self.aired else "claim"
            self.aired[claim.id.root] = span_id
            self.late.put_nowait((kind, claim, span_id))

    def corrected(self, claim: Claim, span_id: str | None) -> None:
        """A claim was corrected or blocked: a verdict with the `correction`, if it is on screen. A
        claim not yet aired goes out later in its corrected form."""
        if claim.id.root in self.aired:
            self.late.put_nowait(("verdict", claim, span_id))

    def audited(self, claim: Claim, span_id: str | None) -> None:
        """An audit landed: tell the viewer only if the claim is already on screen."""
        if claim.id.root in self.aired:
            self.late.put_nowait(("verdict", claim, span_id))


def _claim_data(claim: Claim) -> dict[str, Any]:
    data: dict[str, Any] = claim.model_dump(
        mode="json", by_alias=True, exclude_none=True
    )
    return data


async def _air_beat(msg: StreamMessage, track: _AgentTrack) -> list[StreamMessage]:
    """The beat message with the Producer's rank, then any notice the beat calls for. Starts the
    beat's claims on their way."""
    assert isinstance(msg.data, Beat)
    beat_id = msg.data.id.root
    decision = await track.run.decision(beat_id, PRODUCER_WAIT_S)
    out: list[StreamMessage] = []
    if decision is not None and decision.rank is not None:
        raw = json.loads(msg.model_dump_json(by_alias=True, exclude_none=True))
        raw["data"]["rank"] = decision.rank
        msg = StreamMessage.model_validate(raw)
    out.append(track.number(msg))
    if decision is not None and decision.narrate:
        task = asyncio.ensure_future(track.follow(beat_id))
        track.followers.add(task)
        task.add_done_callback(track.followers.discard)
    if (
        decision is not None
        and decision.reason == "token_cap"
        and not track.told_paused
    ):
        track.told_paused = True
        out.append(track.notice(PAUSED_TEXT))
    if track.run.down and not track.told_down:
        track.told_down = True
        out.append(track.notice(UNAVAILABLE_TEXT))
    return out


async def _hold_for_checks(track: _AgentTrack) -> AsyncGenerator[StreamMessage, None]:
    """Before full time, wait for the audits and corrections still running (up to FULL_TIME_HOLD_S),
    sending what lands. The SSE layer sends a heartbeat for every HEARTBEAT_S of silence."""
    run = track.run
    if not isinstance(run, MatchRun):
        return
    loop = asyncio.get_running_loop()
    deadline = loop.time() + FULL_TIME_HOLD_S
    while run.ledger.pending > 0 and loop.time() < deadline:
        getter = asyncio.ensure_future(track.late.get())
        await asyncio.wait({getter}, timeout=min(HOLD_POLL_S, deadline - loop.time()))
        if not getter.cancel():  # it finished first: the message is ours to send
            yield track.from_late(getter.result())
    for late_msg in track.drain():
        yield late_msg


async def run_live(
    brief: MatchBrief,
    speed: int = SPEED_FAST,
    *,
    pacer: Pacer | None = None,
    after_seq: int = -1,
    store: MatchStore | None = None,
    agents: MatchRun | DownRun | None = None,
    until_s: float | None = None,
) -> AsyncGenerator[StreamMessage, None]:
    """The match as stream messages, each sent when its turn on the timeline comes.

    `after_seq` skips every message up to and including that seq without waiting; the clock then
    starts from the first message that is sent. Resume with the same `speed`: it decides which frames
    are thinned, so it decides the numbering. With a `store`, the match is registered in it and
    filled in as the pipeline advances. With `agents`, beats go to the workflow as they are found
    and their claims follow them on the stream (needs a `store`: the agents read it). `until_s` plays
    only the first part of the match (tests).
    """
    if speed not in SPEEDS:
        raise ValueError(f"speed must be one of {SPEEDS}, not {speed}")
    pacer = pacer or RealPacer()
    queue: asyncio.Queue[Posted] = asyncio.Queue()
    control = _Control()
    on_beat = agents.submit if agents is not None else None
    worker = threading.Thread(
        target=_produce,
        args=(
            brief,
            asyncio.get_running_loop(),
            queue,
            control,
            store,
            on_beat,
            until_s,
        ),
        name=f"pipeline-{brief.match_id}",
        daemon=True,
    )
    worker.start()
    plan = schedule(_Feed(queue), speed, control)
    track = _AgentTrack(agents, after_seq + 1) if agents is not None else None
    unsubscribe_audits = agents.subscribe(track.audited) if agents and track else None
    unsubscribe_corrections = (
        agents.subscribe_corrections(track.corrected) if agents and track else None
    )
    origin: float | None = None
    try:
        async for due, msg in plan:
            if msg.seq <= after_seq:
                continue
            if origin is None:
                origin = pacer.now() - due
            if track is None:
                await pacer.sleep_until(origin + due)
            else:
                # Claims that land while we wait for this message's turn are sent as they land.
                sleeper = asyncio.ensure_future(pacer.sleep_until(origin + due))
                while True:
                    getter = asyncio.ensure_future(track.late.get())
                    waiting: set[asyncio.Future[Any]] = {sleeper, getter}
                    await asyncio.wait(waiting, return_when=asyncio.FIRST_COMPLETED)
                    if getter.done():
                        yield track.from_late(getter.result())
                    else:
                        getter.cancel()
                    if sleeper.done():
                        break
                for late_msg in track.drain():
                    yield late_msg
            if store is not None:
                store.set_playback(brief.match_id, msg.t.root)
            if track is None:
                yield msg
            elif msg.type.value == "beat":
                for sent in await _air_beat(msg, track):
                    yield sent
            else:
                if isinstance(msg.data, Status) and msg.data.state == State.full_time:
                    async for held in _hold_for_checks(track):
                        yield held
                yield track.number(msg)
        if track is not None:
            # Full time: let the checks still running finish and be sent. Audits are not waited for.
            while track.followers or not track.late.empty():
                for late_msg in track.drain():
                    yield late_msg
                if track.followers:
                    await asyncio.wait(set(track.followers), timeout=DRAIN_TIMEOUT_S)
                    if track.followers:
                        break
            for late_msg in track.drain():
                yield late_msg
    finally:
        control.cancel()
        if unsubscribe_audits is not None:
            unsubscribe_audits()
        if unsubscribe_corrections is not None:
            unsubscribe_corrections()
        if track is not None:
            for task in track.followers:
                task.cancel()
        await plan.aclose()
