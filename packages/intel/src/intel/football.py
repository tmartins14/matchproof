"""Football definitions shared by the extractors, on absolute pitch coordinates (ADR 0007).

The home side attacks toward x = 120, the away side toward x = 0. Anything team-relative goes through
the helpers here, never through re-stored data.
"""

import math

from contracts.models import Event
from sim.geometry import PITCH_LENGTH
from sim.positions import WINNING_TYPES

Pt = tuple[float, float]

SIDES = ("home", "away")
PITCH_WIDTH = 80.0
HALFWAY_X = PITCH_LENGTH / 2
GOAL_Y = PITCH_WIDTH / 2  # both goals are centred on the touchline midpoint
GOAL_HALF_WIDTH_M = 3.66  # half of the 7.32 m goal mouth
FINAL_THIRD_DEPTH_M = (
    40.0  # the attacking third is this deep, measured from the opponent's goal line
)
HIGH_TURNOVER_DISTANCE_M = (
    40.0  # a ball won this close to the opponent's goal is a high turnover
)
# Event types that put a player on the ball; pressures, fouls and cards do not count as touches.
TOUCH_TYPES = frozenset(
    {
        "pass",
        "carry",
        "shot",
        "tackle",
        "interception",
        "duel",
        "clearance",
        "corner",
        "free_kick",
        "throw_in",
        "goal_kick",
        "kick_off",
    }
)


def opponent(side: str) -> str:
    return "away" if side == "home" else "home"


def attack_sign(side: str) -> float:
    """+1 when the side attacks toward increasing x, -1 when toward decreasing x."""
    return 1.0 if side == "home" else -1.0


def goal_point(side: str) -> Pt:
    """The centre of the goal that `side` attacks."""
    return (PITCH_LENGTH if side == "home" else 0.0, GOAL_Y)


def distance_to_goal(side: str, at: Pt) -> float:
    """Metres from a point to the centre of the goal `side` attacks."""
    gx, gy = goal_point(side)
    return math.hypot(gx - at[0], gy - at[1])


def in_opponent_half(side: str, x: float) -> bool:
    return attack_sign(side) * (x - HALFWAY_X) > 0


def in_attacking_third(side: str, x: float) -> bool:
    if side == "home":
        return x >= PITCH_LENGTH - FINAL_THIRD_DEPTH_M
    return x <= FINAL_THIRD_DEPTH_M


def location(e: Event) -> Pt:
    return (e.location.root[0].root, e.location.root[1].root)


def end_location(e: Event) -> Pt | None:
    if e.end_location is None:
        return None
    return (e.end_location.root[0].root, e.end_location.root[1].root)


def is_complete_pass(e: Event) -> bool:
    return (
        e.type.value == "pass"
        and e.outcome is not None
        and e.outcome.value == "complete"
    )


def is_ball_won(e: Event) -> bool:
    return (
        e.type.value in WINNING_TYPES
        and e.outcome is not None
        and e.outcome.value == "won"
    )
