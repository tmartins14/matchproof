"""Source rows in words a viewer reads.

An aggregate's `description` is for the API and the MCP server: it says how the facts were measured
("Events and 1 Hz samples in the 900 seconds before ev-001484"). A viewer is told what stretch of
play stood behind a fact: "Play in the 15 minutes before Rivermouth's goal (86′)". The labels are
built from the source id and the match's events, so an archived match gets them too.
"""

import re

from .desk import BUCKET_COUNT, bucket_bounds
from .display import render_clock
from .extract_positions import AGG_POSITION_SAMPLES
from .labels import LabelContext, anchor_phrase
from .since import BEFORE_S
from .windows import period_bounds

SECONDS_PER_MINUTE = 60
BEFORE = re.compile(r"^agg-before_ev_(?P<ev>\d{6})$")
SINCE = re.compile(r"^agg-since_ev_(?P<ev>\d{6})_to_t(?P<whole>\d+)_(?P<frac>\d+)$")
LAST = re.compile(
    r"^agg-last_(?P<minutes>\d+(?:_\d+)?)m_to_t(?P<whole>\d+)_(?P<frac>\d+)$"
)
RUNNING = re.compile(r"^agg-running_to_(?P<minute>\d+)$")
MOMENTUM = re.compile(r"^agg-momentum_min_(?P<number>\d{2})$")
POSITIONS_LABEL = "Where the players stood through the match"
FALLBACK_LABEL = "Match data"


def _clock(t: float) -> str:
    return render_clock(t, "en")[0]


def aggregate_label(agg_id: str, ctx: LabelContext) -> str:
    """The viewer's name for an aggregate source."""
    if agg_id == AGG_POSITION_SAMPLES:
        return POSITIONS_LABEL
    if m := BEFORE.match(agg_id):
        minutes = BEFORE_S / SECONDS_PER_MINUTE
        return f"Play in the {minutes:g} minutes before {anchor_phrase('ev-' + m['ev'], ctx)}"
    if m := SINCE.match(agg_id):
        now = float(f"{m['whole']}.{m['frac']}")
        return f"Play from {anchor_phrase('ev-' + m['ev'], ctx)} to {_clock(now)}"
    if m := LAST.match(agg_id):
        minutes = float(m["minutes"].replace("_", "."))
        return f"Play in the {minutes:g} minutes to {_clock(float(m['whole'] + '.' + m['frac']))}"
    if m := RUNNING.match(agg_id):
        return f"Play up to {m['minute']}′"
    if m := MOMENTUM.match(agg_id):
        number = int(m["number"])
        if 1 <= number <= BUCKET_COUNT:
            bounds = period_bounds(ctx.events.values())
            period = 1 if number <= BUCKET_COUNT // 2 else 2
            if period in bounds:
                start, end = bounds[period]
                t_from, t_to = bucket_bounds(number, start, end)
                return f"Play from {_clock(t_from)} to {_clock(t_to)}"
    return FALLBACK_LABEL


def window_label(t_from: float, t_to: float) -> str:
    return f"Play from {_clock(t_from)} to {_clock(t_to)}"


def freeze_frame_label(event_id: str, ctx: LabelContext) -> str:
    event = ctx.events.get(event_id)
    return (
        f"Where everyone stood at {_clock(event.t.root)}"
        if event
        else "Where everyone stood"
    )


__all__ = ["aggregate_label", "freeze_frame_label", "window_label"]
