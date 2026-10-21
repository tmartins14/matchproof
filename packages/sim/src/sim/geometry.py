"""The one definition of each positional measure, on absolute pitch coordinates (120 x 80, ADR 0007).

Calibration uses these now; the positional extractors import the same functions later.
Outfield means every player of a side except the goalkeeper (shirt 01). The home side attacks toward x = 120.
"""

from collections.abc import Iterable, Sequence
from statistics import mean, median

from contracts.models import PositionFrame

Pt = tuple[float, float]

PITCH_LENGTH = 120.0
POSITION_AGGREGATE = (
    "median"  # how sampled frames of a positional measure are combined, everywhere
)
GOALKEEPER_ID_SUFFIX = "-01"


def outfield_points(frame: PositionFrame, side: str) -> list[Pt]:
    """Positions of a side's outfield players in a frame."""
    return [
        (p.at.root[0].root, p.at.root[1].root)
        for p in frame.players
        if p.side.value == side and not p.id.root.endswith(GOALKEEPER_ID_SUFFIX)
    ]


def back_line_height(points: Iterable[Pt], side: str) -> float:
    """Distance from a side's own goal line to its deepest outfielder."""
    xs = [x for x, _ in points]
    return min(xs) if side == "home" else PITCH_LENGTH - max(xs)


def team_length(points: Iterable[Pt]) -> float:
    """Distance along the pitch from the deepest to the highest outfielder."""
    xs = [x for x, _ in points]
    return max(xs) - min(xs)


def team_width(points: Iterable[Pt]) -> float:
    """Distance across the pitch between the outfielders furthest apart."""
    ys = [y for _, y in points]
    return max(ys) - min(ys)


def hull_area(points: Iterable[Pt]) -> float:
    """Area in m² of the convex hull around the points."""
    pts = sorted(set(points))
    if len(pts) < 3:
        return 0.0

    def half(seq: list[Pt]) -> list[Pt]:
        out: list[Pt] = []
        for q in seq:
            while len(out) >= 2 and (
                (out[-1][0] - out[-2][0]) * (q[1] - out[-2][1])
                - (out[-1][1] - out[-2][1]) * (q[0] - out[-2][0])
                <= 0
            ):
                out.pop()
            out.append(q)
        return out

    hull = half(pts)[:-1] + half(pts[::-1])[:-1]
    return (
        abs(
            sum(
                a[0] * b[1] - b[0] * a[1]
                for a, b in zip(hull, hull[1:] + hull[:1], strict=False)
            )
        )
        / 2
    )


def aggregate(values: Sequence[float]) -> float:
    """Combine a measure's per-frame values the one way calibration and the facts both do."""
    if not values:
        return float("nan")
    return median(values) if POSITION_AGGREGATE == "median" else mean(values)
