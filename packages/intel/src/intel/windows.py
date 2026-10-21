"""Fixed 15-minute windows of the match clock, win-01 to win-06 (three per half).

The last window of each half runs to the end of that half, stoppage included. The clock is continuous
across halves, so the second half's windows start at its period_start event.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from contracts.models import Event

WINDOW_S = 900.0  # length of a fixed window, seconds
WINDOWS_PER_PERIOD = 3  # the third window of a half absorbs the rest of the half
WINDOW_COUNT = 2 * WINDOWS_PER_PERIOD


@dataclass(frozen=True)
class Window:
    id: str
    period: int
    t_from: float
    t_to: float


def window_id(number: int) -> str:
    return f"win-{number:02d}"


def build_window(number: int, period_start: float, period_end: float | None) -> Window:
    """Window `number` (1-6) of a half that starts at period_start. period_end is needed for the third."""
    index = (number - 1) % WINDOWS_PER_PERIOD
    t_from = period_start + WINDOW_S * index
    if index == WINDOWS_PER_PERIOD - 1:
        if period_end is None:
            raise ValueError("the last window of a half needs the end of the half")
        t_to = period_end
    else:
        t_to = t_from + WINDOW_S
    return Window(
        window_id(number), (number - 1) // WINDOWS_PER_PERIOD + 1, t_from, t_to
    )


def event_window_number(period: int, t: float, p2_start: float | None) -> int:
    """Window number (1-6) of an event, from its own period so a period_end stays in its half."""
    if period == 1:
        return min(int(t // WINDOW_S), WINDOWS_PER_PERIOD - 1) + 1
    start = 0.0 if p2_start is None else p2_start
    return (
        WINDOWS_PER_PERIOD
        + min(int((t - start) // WINDOW_S), WINDOWS_PER_PERIOD - 1)
        + 1
    )


def time_window_number(t: float, p2_start: float | None) -> int:
    """Window number (1-6) of a bare time such as a frame, from where the second half starts."""
    if p2_start is not None and t >= p2_start:
        return event_window_number(2, t, p2_start)
    return event_window_number(1, t, p2_start)


def window_ids(first: int, last: int) -> tuple[str, ...]:
    return tuple(window_id(n) for n in range(first, last + 1))


def period_bounds(events: Iterable[Event]) -> dict[int, tuple[float, float]]:
    """Start and end time of each half seen in the events."""
    bounds: dict[int, tuple[float, float]] = {}
    for e in events:
        p, t = e.period.value, e.t.root
        lo, hi = bounds.get(p, (t, t))
        bounds[p] = (min(lo, t), max(hi, t))
    return bounds


def windows(events: Iterable[Event]) -> list[Window]:
    """The window table for a match."""
    out: list[Window] = []
    for period, (start, end) in sorted(period_bounds(events).items()):
        for k in range(WINDOWS_PER_PERIOD):
            out.append(
                build_window((period - 1) * WINDOWS_PER_PERIOD + k + 1, start, end)
            )
    return out
