"""Whole-match extraction in one go (extract_all) and as the match streams (FactEngine).

Both paths build the same spans and call the same extractor functions on them, so at full time
their registries are equal. Facts that depend on a "since X" anchor are not made here; see since.py.
"""

from collections import defaultdict
from collections.abc import Iterable, Mapping

from contracts.models import Event, Fact, PositionFrame

from .extract_events import EventObserver, Span, span_facts
from .extract_positions import (
    AGG_POSITION_SAMPLES,
    AGG_POSITION_SAMPLES_DESCRIPTION,
    FREEZE_FACT_TYPES,
    Sample,
    freeze_facts,
    make_sample,
    position_facts,
)
from .registry import FactRegistry
from .windows import (
    WINDOWS_PER_PERIOD,
    Window,
    build_window,
    event_window_number,
    period_bounds,
    time_window_number,
    window_ids,
    windows,
)


def new_registry() -> FactRegistry:
    registry = FactRegistry()
    registry.register_aggregate(AGG_POSITION_SAMPLES, AGG_POSITION_SAMPLES_DESCRIPTION)
    return registry


def window_span(w: Window) -> Span:
    return Span(w.id, w.period, w.t_from, w.t_to, (w.id,))


def period_span(period: int, t_from: float, t_to: float) -> Span:
    first = (period - 1) * WINDOWS_PER_PERIOD + 1
    return Span(
        f"p{period}",
        period,
        t_from,
        t_to,
        window_ids(first, first + WINDOWS_PER_PERIOD - 1),
    )


def match_span(t_from: float, t_to: float, periods: Iterable[int]) -> Span:
    ids = tuple(
        i
        for p in sorted(periods)
        for i in window_ids((p - 1) * WINDOWS_PER_PERIOD + 1, p * WINDOWS_PER_PERIOD)
    )
    return Span("match", None, t_from, t_to, ids)


def extract_all(
    events: Iterable[Event],
    frames: Iterable[PositionFrame],
    freeze_frames: Iterable[PositionFrame],
    roster: Mapping[str, str] | None = None,
    teams: Mapping[str, str] | None = None,
) -> FactRegistry:
    """Every precomputed fact for a finished match. `roster` maps player ids to names, `teams` sides
    to club names."""
    evs = list(events)
    registry = new_registry()
    bounds = period_bounds(evs)
    p2_start = bounds[2][0] if 2 in bounds else None
    table = windows(evs)
    by_window: dict[int, list[Event]] = defaultdict(list)
    for e in evs:
        by_window[event_window_number(e.period.value, e.t.root, p2_start)].append(e)
    samples: dict[int, list[Sample]] = defaultdict(list)
    for frame in frames:
        sample = make_sample(frame)
        if sample is not None:
            samples[time_window_number(sample.t, p2_start)].append(sample)

    for w in table:
        n = int(w.id.removeprefix("win-"))
        for f in span_facts(by_window[n], window_span(w)):
            registry.add(f)
        for f in position_facts(samples[n], window_span(w)):
            registry.add(f)
    for period, (start, end) in sorted(bounds.items()):
        first = (period - 1) * WINDOWS_PER_PERIOD + 1
        in_period = [
            e for n in range(first, first + WINDOWS_PER_PERIOD) for e in by_window[n]
        ]
        for f in span_facts(in_period, period_span(period, start, end)):
            registry.add(f)
    if bounds:
        everything = [e for n in sorted(by_window) for e in by_window[n]]
        span = match_span(
            min(s for s, _ in bounds.values()),
            max(e for _, e in bounds.values()),
            bounds,
        )
        for f in span_facts(everything, span):
            registry.add(f)
        every_sample = [x for n in sorted(samples) for x in samples[n]]
        for f in position_facts(every_sample, span):
            registry.add(f)

    observer = EventObserver(roster, teams)
    for e in evs:
        for f in observer.observe(e):
            registry.add(f)
    by_id = {e.id.root: e for e in evs if e.type.value in FREEZE_FACT_TYPES}
    for ff in freeze_frames:
        owner = by_id.get(ff.freeze_frame_of.root) if ff.freeze_frame_of else None
        if owner is not None:
            for f in freeze_facts(owner, ff):
                registry.add(f)
    return registry


class FactEngine:
    """Takes the match in time order and emits each fact as soon as its span has closed.

    Window facts appear when the window closes, half facts at the half's period_end, match facts at
    the second half's. Sequence, shot and card facts appear with their event, freeze-frame facts with
    the freeze frame, which follows its event. Feed `finish()` for a match that stops early.
    """

    def __init__(
        self,
        roster: Mapping[str, str] | None = None,
        teams: Mapping[str, str] | None = None,
    ) -> None:
        self.registry = new_registry()
        self._observer = EventObserver(roster, teams)
        self._period_start: dict[int, float] = {}
        self._period_end: dict[int, float] = {}
        self._p2_start: float | None = None
        self._open = 1
        self._closed: set[int] = set()
        self._events: dict[int, list[Event]] = defaultdict(list)
        self._samples: dict[int, list[Sample]] = defaultdict(list)
        self._pending: dict[str, Event] = {}
        self._last_t: dict[int, float] = {}
        self._match_done = False

    def push(self, item: Event | PositionFrame) -> list[Fact]:
        """Take the next event or frame (freeze frames included); return the facts it added."""
        out: list[Fact] = []
        if isinstance(item, Event):
            period, t = item.period.value, item.t.root
            self._last_t[period] = t
            if item.type.value == "period_start":
                self._period_start[period] = t
                if period == 2:
                    self._p2_start = t
            number = event_window_number(period, t, self._p2_start)
            out += self._advance(number)
            self._events[number].append(item)
            if item.type.value in FREEZE_FACT_TYPES:
                self._pending[item.id.root] = item
            out += self._take(self._observer.observe(item))
            if item.type.value == "period_end":
                out += self._end_period(period, t)
        elif item.freeze_frame_of is not None:
            owner = self._pending.pop(item.freeze_frame_of.root, None)
            if owner is not None:
                out += self._take(freeze_facts(owner, item))
        else:
            sample = make_sample(item)
            if sample is not None:
                number = time_window_number(sample.t, self._p2_start)
                out += self._advance(number)
                self._samples[number].append(sample)
        return out

    def finish(self) -> list[Fact]:
        """Close whatever is still open, for a stream that ended without a period_end."""
        out: list[Fact] = []
        for period in sorted(self._last_t):
            if period not in self._period_end:
                out += self._end_period(period, self._last_t[period])
        if self._period_end:
            out += self._end_match()
        return out

    # ---- closing spans -------------------------------------------------------------------------
    def _take(self, facts: list[Fact]) -> list[Fact]:
        return [f for f in facts if self.registry.add(f)]

    def _advance(self, number: int) -> list[Fact]:
        out: list[Fact] = []
        while self._open < number:
            # A half's last window waits for its period_end, which tells it where it stops.
            if self._open % WINDOWS_PER_PERIOD != 0:
                out += self._close_window(self._open)
            self._open += 1
        return out

    def _close_window(self, number: int) -> list[Fact]:
        if number in self._closed:
            return []
        self._closed.add(number)
        period = (number - 1) // WINDOWS_PER_PERIOD + 1
        w = build_window(
            number, self._period_start.get(period, 0.0), self._period_end.get(period)
        )
        return self._take(
            span_facts(self._events[number], window_span(w))
            + position_facts(self._samples[number], window_span(w))
        )

    def _end_period(self, period: int, t: float) -> list[Fact]:
        self._period_end[period] = t
        first = (period - 1) * WINDOWS_PER_PERIOD + 1
        out: list[Fact] = []
        for number in range(first, first + WINDOWS_PER_PERIOD):
            out += self._close_window(number)
        self._open = max(self._open, first + WINDOWS_PER_PERIOD)
        start = self._period_start.get(period, 0.0)
        in_period = [
            e for n in range(first, first + WINDOWS_PER_PERIOD) for e in self._events[n]
        ]
        out += self._take(span_facts(in_period, period_span(period, start, t)))
        if period == 2:
            out += self._end_match()
        return out

    def _end_match(self) -> list[Fact]:
        if self._match_done:
            return []
        self._match_done = True
        done = set(self._period_end)
        everything = [e for n in sorted(self._events) for e in self._events[n]]
        span = match_span(
            min(self._period_start.get(p, 0.0) for p in done),
            max(self._period_end.values()),
            done,
        )
        every_sample = [x for n in sorted(self._samples) for x in self._samples[n]]
        return self._take(
            span_facts(everything, span) + position_facts(every_sample, span)
        )


def split_freeze(
    frames: Iterable[PositionFrame],
) -> Mapping[str, PositionFrame]:
    """Freeze frames by the id of the event they belong to."""
    return {f.freeze_frame_of.root: f for f in frames if f.freeze_frame_of is not None}
