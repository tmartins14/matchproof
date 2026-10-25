"""Facts the live desk reads at every 5-minute mark: match-to-date totals and momentum.

The match clock is cut into 18 buckets, min-01 to min-18, nine per half. Bucket k ends at 300 * k
seconds; the last bucket of each half (min-09, min-18) runs to the end of that half, stoppage
included, and the second half's first bucket starts at its period_start. Both the batch and the
incremental engine build a bucket's facts from the same events through the functions here.
"""

from collections.abc import Mapping, Sequence

from contracts.models import Event, Fact

from .display import display_value, render_clock
from .extract_events import ON_TARGET, side_values
from .football import SIDES, in_opponent_half, location
from .registry import FactRegistry, build_fact
from .windows import WINDOW_S, WINDOWS_PER_PERIOD, window_id

RUNNING_EXTRACTOR = "extract_running"
MOMENTUM_EXTRACTOR = "extract_momentum"
BUCKET_S = 300.0  # length of a bucket, seconds
BUCKET_MINUTES = 5
BUCKETS_PER_PERIOD = 9
BUCKET_COUNT = 2 * BUCKETS_PER_PERIOD
RUNNING_METRICS = ("possession_share", "shots", "shots_on_target", "xg")
FULL_SHARE = 100.0  # momentum runs inside -FULL_SHARE to FULL_SHARE percentage points
# Added to the denominator so a bucket with a handful of actions cannot read as a landslide:
# 3 actions to 0 is 33 pp, not 100. Six is about the actions a side makes in a quiet minute; chosen
# by eye, not fitted.
MOMENTUM_PRIOR = 6
ATTACKING_TYPES = frozenset({"pass", "carry", "shot"})


def bucket_id(number: int) -> str:
    return f"min-{number:02d}"


def bucket_number(period: int, t: float) -> int:
    """Bucket (1-18) of an event, from its own period so a period_end stays in its half."""
    k = int(t // BUCKET_S) + 1
    if period == 1:
        return min(k, BUCKETS_PER_PERIOD)
    return min(max(k, BUCKETS_PER_PERIOD + 1), BUCKET_COUNT)


def bucket_period(number: int) -> int:
    return (number - 1) // BUCKETS_PER_PERIOD + 1


def is_last_in_period(number: int) -> bool:
    return number % BUCKETS_PER_PERIOD == 0


def bucket_bounds(
    number: int, period_start: float, period_end: float | None
) -> tuple[float, float]:
    """(t_from, t_to) of a bucket. `period_end` is needed for the last bucket of a half; elsewhere
    it only keeps a bucket of a stopped match inside the match."""
    first = (number - 1) % BUCKETS_PER_PERIOD == 0
    t_from = period_start if first else (number - 1) * BUCKET_S
    if is_last_in_period(number):
        if period_end is None:
            raise ValueError("the last bucket of a half needs the end of the half")
        return t_from, period_end
    t_to = number * BUCKET_S
    return t_from, t_to if period_end is None else min(t_to, period_end)


def minute_mark(number: int) -> int:
    """The broadcast minute a bucket closes on: 5, 10, ... 90."""
    return number * BUCKET_MINUTES


def running_name(metric: str, side: str, number: int) -> str:
    return f"{metric}({side}, to {minute_mark(number)}′)"


def momentum_name(number: int) -> str:
    return f"momentum({bucket_id(number)})"


def covered_windows(
    t_to: float,
    period_starts: Mapping[int, float],
    period_ends: Mapping[int, float],
) -> list[tuple[str, float]]:
    """(window id, t_to) of every fixed window that has closed by `t_to`."""
    out: list[tuple[str, float]] = []
    for period, start in sorted(period_starts.items()):
        for index in range(WINDOWS_PER_PERIOD):
            number = (period - 1) * WINDOWS_PER_PERIOD + index + 1
            if index == WINDOWS_PER_PERIOD - 1:
                end = period_ends.get(period)
            else:
                end = start + WINDOW_S * (index + 1)
            if end is not None and end <= t_to:
                out.append((window_id(number), end))
    return out


def attacking_actions(events: Sequence[Event], side: str) -> int:
    """Every pass, carry and shot that starts in the opposition half."""
    return sum(
        1
        for e in events
        if e.side.value == side
        and e.type.value in ATTACKING_TYPES
        and in_opponent_half(side, location(e)[0])
    )


def momentum_value(events: Sequence[Event]) -> float:
    """(home - away) / (home + away + MOMENTUM_PRIOR) * 100, rounded to a whole number of
    percentage points. Equal counts give 0; no bucket reaches 100 or -100."""
    home = attacking_actions(events, "home")
    away = attacking_actions(events, "away")
    return display_value(
        FULL_SHARE * (home - away) / (home + away + MOMENTUM_PRIOR), "pp"
    )


def running_facts(
    registry: FactRegistry,
    events: Sequence[Event],
    number: int,
    t_to: float,
    windows_done: Sequence[tuple[str, float]],
) -> list[Fact]:
    """Match-to-date facts for both sides at the end of bucket `number`. `events` run from
    kick-off to the bucket's end. Sources are the windows the total fully covers, plus an aggregate
    for the stretch after the last of them."""
    sources = [w for w, _ in windows_done]
    reach = max((end for _, end in windows_done), default=0.0)
    if reach < t_to:
        agg = f"agg-running_to_{minute_mark(number)}"
        registry.register_aggregate(
            agg,
            f"Events from {render_clock(reach, 'en')[0]} up to {minute_mark(number)}′, "
            "after the last closed window",
        )
        sources.append(agg)
    period = bucket_period(number)
    facts: list[Fact] = []
    for side in SIDES:
        values = {m: (v, u) for m, v, u in side_values(events, side)}
        on_target = sum(
            1
            for e in events
            if e.side.value == side
            and e.type.value == "shot"
            and e.outcome is not None
            and e.outcome.value in ON_TARGET
        )
        values["shots_on_target"] = (on_target, "count")
        scope: dict[str, object] = {
            "side": side,
            "period": period,
            "t_from": 0.0,
            "t_to": t_to,
        }
        for metric in RUNNING_METRICS:
            if metric not in values:
                continue
            value, unit = values[metric]
            facts.append(
                build_fact(
                    running_name(metric, side, number),
                    value,
                    unit,
                    sources,
                    RUNNING_EXTRACTOR,
                    scope,
                )
            )
    return facts


def momentum_facts(
    registry: FactRegistry,
    events: Sequence[Event],
    number: int,
    t_from: float,
    t_to: float,
) -> list[Fact]:
    """The momentum fact of one closed bucket."""
    agg = f"agg-momentum_{bucket_id(number).replace('-', '_')}"
    registry.register_aggregate(
        agg,
        f"Events from {render_clock(t_from, 'en')[0]} to {render_clock(t_to, 'en')[0]}, "
        f"the {BUCKET_MINUTES}-minute bucket {bucket_id(number)}",
    )
    scope: dict[str, object] = {
        "period": bucket_period(number),
        "t_from": t_from,
        "t_to": t_to,
    }
    return [
        build_fact(
            momentum_name(number),
            momentum_value(events),
            "pp",
            [agg],
            MOMENTUM_EXTRACTOR,
            scope,
        )
    ]


def is_desk_fact(fact: Fact) -> bool:
    """Running totals and momentum: the facts the desk draws without a beat citing them."""
    return fact.extractor.name in (RUNNING_EXTRACTOR, MOMENTUM_EXTRACTOR)
