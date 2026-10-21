"""Positional extractors: team shape per window from 1 Hz samples of the 5 Hz frames, and freeze-frame facts.

The shape measures come from sim.geometry, the one definition calibration also uses.
"""

import math
from collections.abc import Sequence
from typing import NamedTuple

from contracts.models import Event, Fact, PositionFrame
from sim.geometry import (
    aggregate,
    back_line_height,
    hull_area,
    outfield_points,
    team_length,
    team_width,
)
from sim.positions import freeze_source_id

from .extract_events import Span
from .football import (
    GOAL_HALF_WIDTH_M,
    SIDES,
    Pt,
    attack_sign,
    end_location,
    goal_point,
    is_complete_pass,
    location,
    opponent,
)
from .registry import build_fact

EXTRACTOR = "extract_positions"
FREEZE_EXTRACTOR = "extract_freeze_frames"
SAMPLE_HZ = 1  # frames are 5 Hz; shape is measured on one frame per second
SAMPLE_TOLERANCE = (
    1e-6  # float slack when deciding a frame time is on the sampling grid
)
MIN_OUTFIELD_PLAYERS = (
    3  # a frame with fewer outfielders has no shape, as in calibration
)
MIN_PHASE_SAMPLES = (
    5  # fewer samples than this in a window and phase and no shape fact is made
)
DEFENSIVE_LINE_PLAYERS = 4  # the deepest outfielders that make up the defensive line
MIDFIELD_LINE_PLAYERS = 4  # the next deepest outfielders, the midfield line
ZONE_DEPTH_M = (
    30.0  # the zone ahead of the ball that attackers v defenders is counted in
)
ZONE_HALF_WIDTH_M = 20.0  # half the width of that zone, either side of the ball
DRAW_RADIUS_M = 4.0  # defenders this close to the ball are drawn to it
PASS_CORRIDOR_HALF_WIDTH_M = (
    10.0  # opponents this close to a pass line are bypassed by it
)
AGG_POSITION_SAMPLES = "agg-position_samples"
AGG_POSITION_SAMPLES_DESCRIPTION = (
    "Outfield positions of both sides, one frame per second of the 5 Hz stream"
)
# Event types that get freeze-frame facts when they are first seen; others on demand via freeze_facts().
FREEZE_FACT_TYPES = frozenset(
    {"shot", "corner", "free_kick", "tackle", "interception", "duel", "card", "pass"}
)

PHASES = ("in_possession", "out_of_possession")
METRICS = (
    "back_line_height",
    "team_length",
    "team_width",
    "compactness",
    "line_gap",
)
POSITION_UNITS = {
    "back_line_height": "m",
    "team_length": "m",
    "team_width": "m",
    "compactness": "m2",
    "line_gap": "m",
}
FREEZE_METRICS = (
    "freeze_frame.home_ahead_of_ball",
    "freeze_frame.away_ahead_of_ball",
    "freeze_frame.attackers_ahead_of_ball",
    "freeze_frame.zone_attackers",
    "freeze_frame.zone_defenders",
    "freeze_frame.attackers_v_defenders",
    "freeze_frame.defenders_between_ball_and_goal",
    "freeze_frame.defenders_drawn",
    "freeze_frame.shooter_nearest_defender",
    "freeze_frame.players_bypassed",
)


class Shape(NamedTuple):
    """One side's shape in one sampled frame."""

    back_line: float
    length: float
    width: float
    area: float
    line_gap: float | None  # None with too few outfielders to form both lines


class Sample(NamedTuple):
    """A sampled frame reduced to what the shape facts need."""

    t: float
    possession: str
    home: Shape | None
    away: Shape | None


def is_sample_time(t: float) -> bool:
    """True when a frame at t is on the SAMPLE_HZ grid."""
    k = t * SAMPLE_HZ
    return abs(k - round(k)) < SAMPLE_TOLERANCE


def depth(side: str, x: float) -> float:
    """Distance from a side's own goal line along the pitch."""
    return x if side == "home" else 120.0 - x


def _shape(points: list[Pt], side: str) -> Shape | None:
    if len(points) < MIN_OUTFIELD_PLAYERS:
        return None
    depths = sorted(depth(side, x) for x, _ in points)
    defence = depths[:DEFENSIVE_LINE_PLAYERS]
    midfield = depths[
        DEFENSIVE_LINE_PLAYERS : DEFENSIVE_LINE_PLAYERS + MIDFIELD_LINE_PLAYERS
    ]
    gap = (
        sum(midfield) / len(midfield) - sum(defence) / len(defence)
        if midfield
        else None
    )
    return Shape(
        back_line_height(points, side),
        team_length(points),
        team_width(points),
        hull_area(points),
        gap,
    )


def make_sample(frame: PositionFrame) -> Sample | None:
    """The sample for a 5 Hz frame, or None when the frame is off the sampling grid."""
    t = frame.t.root
    if not is_sample_time(t):
        return None
    return Sample(
        t,
        frame.possession.value if frame.possession is not None else "",
        _shape(outfield_points(frame, "home"), "home"),
        _shape(outfield_points(frame, "away"), "away"),
    )


def position_values(
    samples: Sequence[Sample], side: str, phase: str
) -> list[tuple[str, float, str]]:
    """Shape of a side, aggregated as calibration does, over the samples where it was in or out of possession."""
    want = phase == "in_possession"
    shapes = [
        (s.home if side == "home" else s.away)
        for s in samples
        if s.possession and (s.possession == side) == want
    ]
    present = [s for s in shapes if s is not None]
    if len(present) < MIN_PHASE_SAMPLES:
        return []
    out = [
        ("back_line_height", aggregate([s.back_line for s in present])),
        ("team_length", aggregate([s.length for s in present])),
        ("team_width", aggregate([s.width for s in present])),
        ("compactness", aggregate([s.area for s in present])),
    ]
    gaps = [s.line_gap for s in present if s.line_gap is not None]
    if gaps:
        out.append(("line_gap", aggregate(gaps)))
    return [(m, v, POSITION_UNITS[m]) for m, v in out]


def position_facts(samples: Sequence[Sample], span: Span) -> list[Fact]:
    """Per team, per phase shape facts for one span (a window or the whole match)."""
    facts: list[Fact] = []
    for side in SIDES:
        scope: dict[str, object] = {
            "side": side,
            "t_from": span.t_from,
            "t_to": span.t_to,
        }
        if span.period is not None:
            scope["period"] = span.period
        for phase in PHASES:
            for metric, value, unit in position_values(samples, side, phase):
                facts.append(
                    build_fact(
                        f"{metric}({side}, {span.label}, {phase})",
                        value,
                        unit,
                        [*span.source_ids, AGG_POSITION_SAMPLES],
                        EXTRACTOR,
                        scope,
                    )
                )
    return facts


# ---- freeze frames -----------------------------------------------------------------------------
def _all_points(frame: PositionFrame, side: str) -> list[Pt]:
    return [
        (p.at.root[0].root, p.at.root[1].root)
        for p in frame.players
        if p.side.value == side
    ]


def _distance_to_segment(p: Pt, a: Pt, b: Pt) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length2 = dx * dx + dy * dy
    f = (
        0.0
        if length2 == 0
        else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length2))
    )
    return math.hypot(p[0] - (a[0] + f * dx), p[1] - (a[1] + f * dy))


def _in_triangle(p: Pt, a: Pt, b: Pt, c: Pt) -> bool:
    def cross(o: Pt, u: Pt, v: Pt) -> float:
        return (u[0] - o[0]) * (v[1] - o[1]) - (u[1] - o[1]) * (v[0] - o[0])

    signs = (cross(a, b, p), cross(b, c, p), cross(c, a, p))
    return all(s >= 0 for s in signs) or all(s <= 0 for s in signs)


def freeze_facts(event: Event, frame: PositionFrame) -> list[Fact]:
    """Facts from the freeze frame of an event, sourced to its ff- id and the event."""
    eid = event.id.root
    side = event.side.value
    other = opponent(side)
    sign = attack_sign(side)
    sources = [freeze_source_id(eid), eid]
    ball: Pt = (frame.ball.root[0].root, frame.ball.root[1].root)
    mine = outfield_points(frame, side)
    theirs = outfield_points(frame, other)
    scope: dict[str, object] = {
        "side": side,
        "t_from": event.t.root,
        "t_to": event.t.root,
    }

    def ahead(points: list[Pt], who: str) -> int:
        return sum(1 for x, _ in points if attack_sign(who) * (x - ball[0]) > 0)

    def in_zone(p: Pt) -> bool:
        return (
            0 < sign * (p[0] - ball[0]) <= ZONE_DEPTH_M
            and abs(p[1] - ball[1]) <= ZONE_HALF_WIDTH_M
        )

    zone_a = sum(1 for p in mine if in_zone(p))
    zone_d = sum(1 for p in _all_points(frame, other) if in_zone(p))
    gx = goal_point(side)[0]
    cone = (
        ball,
        (gx, goal_point(side)[1] - GOAL_HALF_WIDTH_M),
        (gx, goal_point(side)[1] + GOAL_HALF_WIDTH_M),
    )
    values: list[tuple[str, float | int | str, str]] = [
        ("home_ahead_of_ball", ahead(outfield_points(frame, "home"), "home"), "count"),
        ("away_ahead_of_ball", ahead(outfield_points(frame, "away"), "away"), "count"),
        ("attackers_ahead_of_ball", ahead(mine, side), "count"),
        ("zone_attackers", zone_a, "count"),
        ("zone_defenders", zone_d, "count"),
        ("attackers_v_defenders", f"{zone_a} v {zone_d}", ""),
        (
            "defenders_between_ball_and_goal",
            sum(1 for p in theirs if _in_triangle(p, *cone)),
            "count",
        ),
        (
            "defenders_drawn",
            sum(
                1
                for p in theirs
                if math.hypot(p[0] - ball[0], p[1] - ball[1]) <= DRAW_RADIUS_M
            ),
            "count",
        ),
    ]
    if event.type.value == "shot" and theirs:
        shooter = location(event)
        values.append(
            (
                "shooter_nearest_defender",
                min(math.hypot(p[0] - shooter[0], p[1] - shooter[1]) for p in theirs),
                "m",
            )
        )
    end = end_location(event)
    if is_complete_pass(event) and end is not None:
        start = location(event)
        bypassed = sum(
            1
            for p in theirs
            if sign * (p[0] - start[0]) > 0
            and sign * (p[0] - end[0]) < 0
            and _distance_to_segment(p, start, end) <= PASS_CORRIDOR_HALF_WIDTH_M
        )
        values.append(("players_bypassed", bypassed, "count"))
    return [
        build_fact(
            f"freeze_frame({eid}).{metric}",
            value,
            unit,
            sources,
            FREEZE_EXTRACTOR,
            scope,
        )
        for metric, value, unit in values
    ]
