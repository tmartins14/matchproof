"""On-demand "since X" facts: measures from an anchor event to now, the same measures for the 15
minutes before it, and the change between them. The beat detector calls these when a beat needs them
and the facts join the registry then.

Names carry the time of "now" so that an earlier fact is never overwritten by a later call.
"""

import re
from collections.abc import Iterable, Sequence

from contracts.models import Event, Fact, PositionFrame

from .display import display_value
from .extract_events import side_values
from .extract_positions import (
    Sample,
    is_sample_time,
    make_sample,
    position_values,
)
from .football import SIDES, is_complete_pass
from .registry import FactRegistry, build_fact

EXTRACTOR = "since"
BEFORE_S = (
    900.0  # how far back the "before" comparison reaches from the anchor, seconds
)
LINE_BREAK_MIN_BYPASSED = (
    3  # a completed pass that bypasses this many opponents goes through the lines
)
SECONDS_PER_MINUTE = 60.0
# Event measures reported for each span, and the positional measures (out of possession, where a
# side's shape is a choice rather than a result of having the ball).
EVENT_METRICS = (
    "possession_share",
    "shots",
    "territory",
    "touches_in_opponent_half",
    "high_turnovers",
    "press_rate",
)
POSITION_METRICS = ("back_line_height", "compactness")
CHANGE_NAMES = {
    "back_line_height": "back_line_change",
    "compactness": "compactness_change",
}
METRICS = (
    *EVENT_METRICS,
    "line_breaking_passes",
    *POSITION_METRICS,
    *CHANGE_NAMES.values(),
)
LAST_N_METRICS = EVENT_METRICS


def _agg_id(text: str) -> str:
    return "agg-" + re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _span_facts(
    registry: FactRegistry,
    label: str,
    events: Sequence[Event],
    samples: Sequence[Sample],
    t_from: float,
    t_to: float,
    extra_sources: Sequence[str],
    description: str,
) -> dict[tuple[str, str], Fact]:
    """Facts for one span, added to the registry. Keyed by (side, metric)."""
    agg = _agg_id(label)
    registry.register_aggregate(agg, description)
    sources = [*extra_sources, agg]
    found: dict[tuple[str, str], Fact] = {}

    def make(side: str, metric: str, value: float, unit: str) -> None:
        scope: dict[str, object] = {"side": side, "t_from": t_from, "t_to": t_to}
        fact = build_fact(
            f"{metric}({side}, {label})", value, unit, sources, EXTRACTOR, scope
        )
        registry.add(fact)
        found[(side, metric)] = registry.by_name(fact.name)

    for side in SIDES:
        for metric, value, unit in side_values(events, side):
            if metric in EVENT_METRICS:
                make(side, metric, value, unit)
        passes = 0
        for e in events:
            if e.side.value == side and is_complete_pass(e):
                bypassed = _bypassed(registry, e.id.root)
                if bypassed is not None and bypassed >= LINE_BREAK_MIN_BYPASSED:
                    passes += 1
        make(side, "line_breaking_passes", passes, "count")
        for metric, value, unit in position_values(samples, side, "out_of_possession"):
            if metric in POSITION_METRICS:
                make(side, metric, value, unit)
    return found


def _bypassed(registry: FactRegistry, event_id: str) -> int | None:
    name = f"freeze_frame({event_id}).players_bypassed"
    if not registry.has_name(name):
        return None
    value = registry.by_name(name).value
    return int(value) if isinstance(value, int | float) else None


def _samples(frames: Iterable[PositionFrame]) -> list[Sample]:
    out = []
    for f in frames:
        if is_sample_time(f.t.root):
            s = make_sample(f)
            if s is not None:
                out.append(s)
    return out


def since(
    anchor_event_id: str,
    registry: FactRegistry,
    events: Sequence[Event],
    frames: Iterable[PositionFrame],
) -> list[Fact]:
    """Facts from the anchor to now, the same facts for the 15 minutes before, and change facts.

    `events` and `frames` are everything seen so far. Returns every fact it made, adding them to the
    registry. Positional measures are for the out-of-possession phase; counts are not compared
    across spans of different length, so only back_line_height and compactness get change facts.
    """
    anchor = next(e for e in events if e.id.root == anchor_event_id)
    samples = _samples(frames)
    now = max([e.t.root for e in events] + [s.t for s in samples])
    t0 = anchor.t.root
    before_events = [
        e for e in events if e.seq < anchor.seq and e.t.root >= t0 - BEFORE_S
    ]
    since_events = [e for e in events if e.seq > anchor.seq]
    before_label = f"before {anchor_event_id}"
    since_label = f"since {anchor_event_id} to t{now:.2f}"
    before = _span_facts(
        registry,
        before_label,
        before_events,
        [s for s in samples if t0 - BEFORE_S <= s.t < t0],
        max(t0 - BEFORE_S, 0.0),
        t0,
        [anchor_event_id],
        f"Events and 1 Hz samples in the {BEFORE_S:.0f} seconds before {anchor_event_id}",
    )
    after = _span_facts(
        registry,
        since_label,
        since_events,
        [s for s in samples if s.t >= t0],
        t0,
        now,
        [anchor_event_id],
        f"Events and 1 Hz samples from {anchor_event_id} to match time {now:.2f}",
    )
    made = list(before.values()) + list(after.values())
    for side in SIDES:
        for metric, change_name in CHANGE_NAMES.items():
            b, a = before.get((side, metric)), after.get((side, metric))
            if b is None or a is None:
                continue
            unit = "m2" if metric == "compactness" else "m"
            value = abs(
                display_value(float(b.value), unit)
                - display_value(float(a.value), unit)
            )
            scope: dict[str, object] = {
                "side": side,
                "t_from": max(t0 - BEFORE_S, 0.0),
                "t_to": now,
            }
            fact = build_fact(
                f"{change_name}({side}, {anchor_event_id}, to t{now:.2f})",
                value,
                unit,
                sorted({s.root for s in (*b.source_ids, *a.source_ids)}),
                EXTRACTOR,
                scope,
            )
            registry.add(fact)
            made.append(registry.by_name(fact.name))
    return made


def last_minutes(
    minutes: float,
    registry: FactRegistry,
    events: Sequence[Event],
) -> list[Fact]:
    """Event measures over the last `minutes` of play, e.g. territory and shots in the last 10."""
    now = events[-1].t.root
    t_from = now - minutes * SECONDS_PER_MINUTE
    label = f"last {minutes:g}m to t{now:.2f}"
    span = [e for e in events if e.t.root > t_from]
    found = _span_facts(
        registry,
        label,
        span,
        [],
        t_from,
        now,
        [events[-1].id.root],
        f"Events in the {minutes:g} minutes up to match time {now:.2f}",
    )
    return [f for (_, metric), f in found.items() if metric in LAST_N_METRICS]
