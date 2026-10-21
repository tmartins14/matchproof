"""The one shape model: where a team's players stand for a given ball, line height and phase.

The engine uses it to pick actors and recipients; positions.py uses it to move the 22 players.
Nothing else computes slot targets, so the events and the frames never disagree about shape.
Everything here is in the team's attacking frame: u is metres toward the goal it attacks, v is lateral.
"""

from dataclasses import dataclass

from .tactics import FORMATIONS

Pt = tuple[float, float]

LINE_SHIFT = 26.0  # how far the outfield shape moves for line_height 0 -> 1, in and out of possession
BALL_PULL = 0.30  # how much a slot follows the ball along the pitch
LATERAL_PULL = 0.25  # how much a slot follows the ball across the pitch
PUSH_IN = 18.0  # in possession: how far the whole outfield steps up the pitch
WIDTH_IN = 0.12  # in possession: extra lateral spread, as a share of distance from the centre line
BACK_OUT = 33.9  # out of possession: depth of the deepest outfielder at line_height 0.5 with the ball on the halfway line
COMPACT_OUT = 0.52  # out of possession: share of the formation's length along the pitch that is closed
WIDTH_OUT = 0.10  # out of possession: share of the formation's width across the pitch that is closed
BACK_FLOOR = 10.0  # out of possession: no outfielder is pulled deeper than this from his goal line...
BOX_U = 18.0  # ...unless the ball is this close to it (inside the defending box)
DOWN_LINE = -0.30  # effective line_height change for each player the team is down
DOWN_COMPACT = (
    0.08  # out of possession: extra share of block length closed for each player down
)
DOWN_WIDTH = (
    0.10  # out of possession: extra share of block width closed for each player down
)
LEAD_MINUTE = 75.0  # from this minute a leading team sits deeper
LEAD_LINE = -0.15  # effective line_height change when leading from LEAD_MINUTE
TRAIL_MINUTE = 70.0  # from this minute a trailing team pushes up
TRAIL_LINE = 0.20  # effective line_height change when trailing from TRAIL_MINUTE, for a team with all 11
PRESS_COMPACT = 0.20  # out of possession: extra share of block length closed per unit of press above 0.5
GK_MAX_U = 18.0  # the goalkeeper stays within this distance of the goal line
GK_BALL_PULL = 0.08  # how much the goalkeeper steps up with the ball
GK_LATERAL = 0.12  # damped lateral tracking of the ball by the goalkeeper
PITCH_MARGIN = 1.0  # targets are kept this far inside the touchlines and goal lines
CENTRE_V = 40.0  # the pitch centre line, lateral


@dataclass(frozen=True)
class GameState:
    """What the shape reacts to, from the team's own point of view."""

    minute: float = 0.0  # match clock, period 2 restarting at 45
    goal_diff: int = 0  # own goals minus the opponent's
    players_down: int = 0  # own players sent off


NEUTRAL = GameState()


def effective_line_height(line_height: float, state: GameState) -> float:
    """The brief's line height moved by the score, the clock and red cards, kept in 0 to 1."""
    lh = line_height + DOWN_LINE * state.players_down
    if state.goal_diff > 0 and state.minute >= LEAD_MINUTE:
        lh += LEAD_LINE
    elif (
        state.goal_diff < 0 and state.minute >= TRAIL_MINUTE and not state.players_down
    ):
        lh += TRAIL_LINE
    return _clamp(lh, 0.0, 1.0)


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _back_anchor(formation: str) -> float:
    """Anchor depth of a formation's deepest outfielder."""
    return min(u for u, _ in FORMATIONS[formation][1:])


def target(
    formation: str,
    slot: int,
    line_height: float,
    ball: Pt,
    in_possession: bool,
    state: GameState = NEUTRAL,
    press: float = 0.5,
) -> Pt:
    """Target point for a slot, in the team's attacking frame, clamped to the pitch."""
    ax, ay = FORMATIONS[formation][slot]
    bu, bv = ball
    if slot == 0:
        u = _clamp(ax + GK_BALL_PULL * (bu - 60.0), PITCH_MARGIN, GK_MAX_U)
        v = _clamp(CENTRE_V + GK_LATERAL * (bv - CENTRE_V), 30.0, 50.0)
        return (u, v)
    shift = (effective_line_height(line_height, state) - 0.5) * LINE_SHIFT
    v = ay + LATERAL_PULL * (bv - ay)
    if in_possession:
        u = ax + PUSH_IN + shift + BALL_PULL * (bu - 60.0)
        v = CENTRE_V + (v - CENTRE_V) * (1.0 + WIDTH_IN)
    else:
        compact = _clamp(
            COMPACT_OUT
            + DOWN_COMPACT * state.players_down
            + PRESS_COMPACT * (press - 0.5),
            0.0,
            0.8,
        )
        narrow = _clamp(WIDTH_OUT + DOWN_WIDTH * state.players_down, 0.0, 0.8)
        u = (
            BACK_OUT
            + (ax - _back_anchor(formation)) * (1.0 - compact)
            + shift
            + BALL_PULL * (bu - 60.0)
        )
        v = CENTRE_V + (v - CENTRE_V) * (1.0 - narrow)
        if bu > BOX_U:
            u = max(u, BACK_FLOOR)
    return (
        _clamp(u, PITCH_MARGIN, 120.0 - PITCH_MARGIN),
        _clamp(v, PITCH_MARGIN, 80.0 - PITCH_MARGIN),
    )
