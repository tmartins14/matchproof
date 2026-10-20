"""The one shape model: where a team's players stand for a given ball, line height and phase.

The engine uses it to pick actors and recipients; positions.py uses it to move the 22 players.
Nothing else computes slot targets, so the events and the frames never disagree about shape.
Everything here is in the team's attacking frame: u is metres toward the goal it attacks, v is lateral.
"""

from .tactics import FORMATIONS

Pt = tuple[float, float]

LINE_SHIFT = 18.0  # how far the outfield shape moves for line_height 0 -> 1, in and out of possession
BALL_PULL = 0.30  # how much a slot follows the ball along the pitch
LATERAL_PULL = 0.25  # how much a slot follows the ball across the pitch
PUSH_IN = 18.0  # in possession: how far the whole outfield steps up the pitch
WIDTH_IN = 0.12  # in possession: extra lateral spread, as a share of distance from the centre line
MID_BLOCK_U = 45.5  # out of possession: depth of the block's centre at line_height 0.5 with the ball on the halfway line
COMPACT_OUT = 0.52  # out of possession: share of the formation's length along the pitch that is closed
WIDTH_OUT = 0.10  # out of possession: share of the formation's width across the pitch that is closed
BACK_FLOOR = 10.0  # out of possession: no outfielder is pulled deeper than this from his goal line...
BOX_U = 18.0  # ...unless the ball is this close to it (inside the defending box)
GK_MAX_U = 18.0  # the goalkeeper stays within this distance of the goal line
GK_BALL_PULL = 0.08  # how much the goalkeeper steps up with the ball
GK_LATERAL = 0.12  # damped lateral tracking of the ball by the goalkeeper
PITCH_MARGIN = 1.0  # targets are kept this far inside the touchlines and goal lines
CENTRE_V = 40.0  # the pitch centre line, lateral


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _outfield_centre(formation: str) -> float:
    """Mean anchor depth of a formation's outfielders."""
    anchors = FORMATIONS[formation][1:]
    return sum(u for u, _ in anchors) / len(anchors)


def target(
    formation: str, slot: int, line_height: float, ball: Pt, in_possession: bool
) -> Pt:
    """Target point for a slot, in the team's attacking frame, clamped to the pitch."""
    ax, ay = FORMATIONS[formation][slot]
    bu, bv = ball
    if slot == 0:
        u = _clamp(ax + GK_BALL_PULL * (bu - 60.0), PITCH_MARGIN, GK_MAX_U)
        v = _clamp(CENTRE_V + GK_LATERAL * (bv - CENTRE_V), 30.0, 50.0)
        return (u, v)
    v = ay + LATERAL_PULL * (bv - ay)
    if in_possession:
        u = ax + PUSH_IN + (line_height - 0.5) * LINE_SHIFT + BALL_PULL * (bu - 60.0)
        v = CENTRE_V + (v - CENTRE_V) * (1.0 + WIDTH_IN)
    else:
        centre = _outfield_centre(formation)
        u = (
            MID_BLOCK_U
            + (ax - centre) * (1.0 - COMPACT_OUT)
            + (line_height - 0.5) * LINE_SHIFT
            + BALL_PULL * (bu - 60.0)
        )
        v = CENTRE_V + (v - CENTRE_V) * (1.0 - WIDTH_OUT)
        if bu > BOX_U:
            u = max(u, BACK_FLOOR)
    return (
        _clamp(u, PITCH_MARGIN, 120.0 - PITCH_MARGIN),
        _clamp(v, PITCH_MARGIN, 80.0 - PITCH_MARGIN),
    )
