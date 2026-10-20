"""Possession-chain match engine.

v1 simplification: only planted beats score. Organic shots that would score are recorded as
saved, wide, blocked or post, so the final score always matches the storyline.

Calibration: organic counts (shots, fouls, corners, xG) are steered toward per-match targets by
pacers, and the constants were tuned until the means across 32 runs sit inside the bands in
packages/sim/calibration/targets.yaml (all provisional; see docs/compliance/DATA.md). Realism won
over the earlier demonstration setting: planted beats still guarantee the storyline's goals.

Internally each team reasons in its own attacking frame (u, v): u is metres toward the goal it
attacks, v is the lateral coordinate. Events are stored in absolute coordinates (ADR 0007): the home
side's frame is the absolute one, the away side's mirrors x to 120 - u and keeps y.
"""

import math
import random
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from contracts.models import Event, MatchBrief

from . import shape
from .tactics import role_of

Pt = tuple[float, float]

# ---- Clock -----------------------------------------------------------------------------------
HALF_SECONDS = 2700.0  # length of each period before stoppage
P1_STOPPAGE_MIN = (1, 4)  # drawn stoppage minutes, period 1
P2_STOPPAGE_MIN = (2, 6)  # drawn stoppage minutes, period 2
BEAT_MARGIN_S = (
    40.0  # slack before a window ends so a natural step cannot push a beat out of it
)
PERIOD_TAIL_S = 20.0  # play kept going after the last scripted beat in a period
# Seconds the clock advances before each event type is emitted: (low, high).
EVENT_DT: dict[str, tuple[float, float]] = {
    "pass": (1.8, 3.8),
    "carry": (1.6, 3.6),
    "shot": (1.2, 2.6),
    "pressure": (0.6, 1.6),
    "tackle": (0.5, 1.4),
    "interception": (0.5, 1.4),
    "duel": (0.6, 1.6),
    "clearance": (0.8, 2.0),
    "foul": (0.8, 2.0),
    "card": (4.0, 9.0),
    "free_kick": (12.0, 24.0),
    "corner": (8.0, 16.0),
    "throw_in": (5.0, 11.0),
    "goal_kick": (8.0, 16.0),
    "kick_off": (30.0, 50.0),
}

# ---- Team behaviour ---------------------------------------------------------------------------
# Possession weight per storyline (home, away); smash_and_grab has Rivermouth dominating the ball.
STORY_POSSESSION: dict[str, tuple[float, float]] = {"smash_and_grab": (1.25, 1.0)}
RED_CARD_WEIGHT = 0.8  # possession weight multiplier after a red card
ROLE_ACTOR_W: dict[str, float] = {
    "gk": 0.2,
    "def": 1.0,
    "mid": 1.4,
    "att": 1.1,
}  # who gets the ball
ROLE_RECEIVE_W: dict[str, float] = {
    "gk": 0.12,
    "def": 0.9,
    "mid": 1.3,
    "att": 1.0,
}  # who receives a pass
PICK_SCALE = 14.0  # distance scale for picking the player who acts near a spot; Gaussian, so far players rarely do

# ---- Passing ----------------------------------------------------------------------------------
PASS_LEN_PATIENT = 14.0  # preferred pass length at directness 0
PASS_LEN_DIRECT = 27.0  # preferred pass length at directness 1
PASS_SPREAD = 12.0  # how tightly recipients cluster around the preferred length
FWD_BASE = -1.92  # forward preference at directness 0
FWD_GAIN = 1.0  # extra forward preference per unit of directness
PASS_COME_SHORT = (
    0.45  # most a receiver closes the gap to the ball, as a share of the distance
)
MIN_PASS = 3.0  # shortest pass considered
HIGH_BASE = 0.04  # share of passes that are high at directness 0 and short length
HIGH_DIRECTNESS = 0.30  # extra high-pass share per unit of directness
HIGH_LENGTH = 0.012  # extra high-pass share per metre beyond 20
LOW_SHARE = 0.18  # share of non-high passes that are low
DIFF_BASE = 0.04  # pass difficulty at zero length
DIFF_LENGTH = 0.0105  # difficulty per metre of pass length
DIFF_PRESSURE = 0.16  # difficulty added when the passer is under pressure
DIFF_HIGH = 0.08  # difficulty added to high passes
COMPLETE_MAX = 0.985  # completion probability at zero difficulty
COMPLETE_SLOPE = 0.5  # completion lost per unit of difficulty
COMPLETE_DIRECTNESS = 0.10  # completion lost per unit of directness above 0.5
SPEED_RANGE: dict[str, tuple[float, float]] = {
    "ground": (8.0, 20.0),
    "low": (11.0, 24.0),
    "high": (14.0, 28.0),
}
SPEED_FULL_LEN = 40.0  # pass length at which speed reaches the top of its range
PROGRESSIVE_GAIN = 10.0  # metres closer to goal that makes a pass progressive
BOX_U = 102.0  # a ball beyond this u, inside the lateral limits, is in the box
BOX_V = (18.0, 62.0)  # lateral limits of the box
# What happens to an incomplete pass: intercepted, out of play, or a loose ball.
INTERCEPT_SHARE = 0.42
OUT_SHARE = 0.18
GOAL_LINE_U = 108.0  # an out-of-play pass ending beyond this u is a goal kick
CARRY_W = 0.9  # weight of carrying the ball in the action choice
PASS_W = 1.0  # weight of passing in the action choice
CARRY_LEN = (3.0, 10.0)  # carry distance range

# ---- Pressing and winning the ball ------------------------------------------------------------
ENGAGE_DEEP = 35.0  # distance from own goal where a deep block starts to engage
ENGAGE_HIGH = 72.0  # distance from own goal where a high line starts to engage
ENGAGE_SOFTNESS = 9.0  # how gradually engagement switches on across the engage depth
BOX_ENGAGE_DEPTH = (
    24.0  # inside this distance from own goal a team always defends the ball
)
BOX_ENGAGE_Z = 0.6  # engagement level when defending near own goal
PRESS_BASE = 0.02  # chance of a pressure event with a 0 press dial
PRESS_GAIN = 0.65  # extra chance of pressure per unit of press dial when fully engaged
TACKLE_BASE = 0.07  # chance a pressure event ends in a won tackle at press 0
TACKLE_GAIN = 0.22  # extra tackle chance per unit of press dial
DUEL_P = 0.12  # chance a pressure event becomes a duel
DUEL_WIN = 0.5  # chance the defender wins that duel, before possession weights
FOUL_P = 0.07  # chance a pressure event becomes a foul
FOUL_BOX_FACTOR = (
    0.3  # fouls near own goal are rarer (v1 awards a free kick, no organic penalties)
)
YELLOW_P = 0.203  # chance a foul earns a yellow
FREE_KICK_SHOT_P = 0.3  # chance a free kick inside shooting range is a shot
FREE_KICK_RANGE = 30.0  # distance to goal inside which a free kick can be a shot
CLEAR_DEPTH = 18.0  # a team winning the ball this close to its own goal may clear it
CLEAR_P = 0.45  # chance it does
CLEAR_LOSS = 0.5  # chance the opponent regains a clearance
UNDER_PRESSURE_MAX = 3  # most defenders committed to one pressure event

# ---- Shooting ---------------------------------------------------------------------------------
SHOT_W = 0.87  # weight of shooting at the goal line, before pacing
SHOT_DECAY = 11.0  # distance scale of the shot weight
SHOT_RANGE = 26.0  # no organic shot from further out than this
GOAL_WIDTH = 8.0  # goal width in pitch units
XG_B0 = -1.25  # logistic intercept for xG
XG_DIST = -0.07  # logistic slope on distance
XG_ANGLE = 0.9  # logistic slope on the angle the goal subtends
XG_HEADER = -0.9  # logistic offset for headers
ORGANIC_XG_MAX = 0.3  # best chance an organic shot can be; bigger ones are planted
XG_RANGE = (0.01, 0.9)  # xG clamp
FOOT_SPEED = (18.0, 34.0)  # shot speed range, m/s
HEADER_SPEED = (10.0, 20.0)  # header speed range, m/s
# Organic outcome weights (saved, wide, blocked, post): a shot that "would score" vs one that would not.
SCORING_OUTCOMES = (0.62, 0.05, 0.23, 0.10)
MISSING_OUTCOMES = (0.22, 0.45, 0.30, 0.03)
CORNER_AFTER_SAVE = 0.6  # chance a saved shot goes behind for a corner
CORNER_AFTER_BLOCK = 0.7  # chance a blocked shot goes behind for a corner
REBOUND_AFTER_POST = 0.5  # chance the attacking side keeps the ball after a post
CORNER_AFTER_DEFLECT = 0.8  # chance a pass that ends behind the goal line was last touched by a defender, giving a corner
CORNER_AFTER_WIDE = 0.3  # chance a wide shot was deflected behind for a corner
CORNER_AFTER_BOX_LOSS = (
    0.3  # chance a pass lost in the box is deflected behind for a corner
)
CORNER_SHOT_P = 0.45  # chance an organic corner produces a header
PENALTY_XG = 0.78  # xG of a penalty

# ---- Pacing -----------------------------------------------------------------------------------
# Counts such as shots and fouls are overdispersed when left to chance: one attacking streak can
# double a team's shots. A pacer scales the chance of each by how far the team is ahead of or behind
# a per-match target (organic events only; planted beats do not count), which keeps
# seed-to-seed spread inside the calibration bands.
MATCH_SECONDS_GUIDE = 5700.0  # expected match length, to turn the clock into a share
SHOT_TARGET = 16.0  # organic shots per team per match the pacer steers toward
FOUL_TARGET = 10.0  # organic fouls per team per match the pacer steers toward
XG_TARGET = 1.61  # total xG per team per match; organic gets what planted beats leave
XG_ORGANIC_MIN = 1.0  # least organic xG a team is steered toward
PLANTED_XG_GUESS = 0.25  # typical xG of a planted goal, to budget organic xG
PLANTED_XG_MIN = 0.1  # planted goals are real chances: xG is never lower than this
PENALTY_EXTRA_SHOTS = 9.0  # extra organic shots targeted for a team with a penalty
CORNER_TARGET = 5.0  # organic corners per team per match the pacer steers toward
PACE_GAIN = 1.2  # how hard the pacer pushes back, per standard deviation off target
XG_PACE_GAIN = 1.5  # pacer gain for xG
XG_PACE_SCALE = 0.4  # xG shortfall or excess that counts as one deviation
PACE_FLOOR = 3.0  # smallest expected count used to scale the shortfall
PACE_RANGE = (0.15, 10.0)  # smallest and largest multiplier the pacer may apply

# ---- Planted beats ----------------------------------------------------------------------------
COUNTER_SECONDS = (8.0, 14.0)  # counter_goal: interception to shot
SET_PIECE_SECONDS = (2.5, 4.0)  # set_piece_goal: corner to header
TURNOVER_SECONDS = (6.0, 10.0)  # high_turnover_goal: pressure to shot
TURNOVER_MAX_DIST = 38.0  # interception must be this close to the opponent's goal
OPEN_PLAY_PASS_DT = (1.8, 3.8)  # open_play_goal: seconds per pass
PENALTY_DELAY = (25.0, 45.0)  # penalty: foul to shot
BEAT_MAX_SECONDS: dict[str, float] = {
    "counter_goal": 14.0,
    "set_piece_goal": 5.0,
    "high_turnover_goal": 12.0,
    "open_play_goal": 28.0,
    "red_card": 14.0,
    "penalty": 50.0,
}


def _dist(a: Pt, b: Pt) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _opp(side: str) -> str:
    return "away" if side == "home" else "home"


def to_abs(side: str, p: Pt) -> Pt:
    """Team frame to absolute coordinates."""
    x = p[0] if side == "home" else 120.0 - p[0]
    return (
        round(x, 1),
        round(p[1], 1),
    )  # locations are kept at 0.1 so recomputed lengths agree


def to_rel(side: str, p: Pt) -> Pt:
    """Absolute coordinates to a team's attacking frame (the mirror is its own inverse)."""
    return to_abs(side, p)


def distance_to_goal(side: str, p_abs: Pt) -> float:
    u, v = to_rel(side, p_abs)
    return math.hypot(120.0 - u, 40.0 - v)


def is_progressive(side: str, start: Pt, end: Pt) -> bool:
    """At least 10 m closer to the opponent's goal, or the ball ends in the box."""
    eu, ev = to_rel(side, end)
    in_box = eu >= BOX_U and BOX_V[0] <= ev <= BOX_V[1]
    return (
        in_box
        or distance_to_goal(side, start) - distance_to_goal(side, end)
        >= PROGRESSIVE_GAIN
    )


def shot_xg(side: str, loc_abs: Pt, header: bool) -> float:
    """Logistic on distance and the angle the goal subtends, clamped."""
    u, v = to_rel(side, loc_abs)
    d = max(120.0 - u, 0.5)
    dy = v - 40.0
    angle = math.atan2(GOAL_WIDTH * d, d * d + dy * dy - (GOAL_WIDTH / 2) ** 2)
    if angle < 0:
        angle += math.pi
    z = (
        XG_B0
        + XG_DIST * math.hypot(d, dy)
        + XG_ANGLE * angle
        + (XG_HEADER if header else 0.0)
    )
    return _clamp(1.0 / (1.0 + math.exp(-z)), *XG_RANGE)


@dataclass
class _Team:
    side: str
    formation: str
    press: float
    directness: float
    line_height: float
    weight: float
    active: set[int] = field(default_factory=lambda: set(range(11)))
    yellows: set[int] = field(default_factory=set)

    def role(self, slot: int) -> str:
        return role_of(self.formation, slot)

    def slots_with(self, *roles: str) -> list[int]:
        return sorted(s for s in self.active if self.role(s) in roles)


@dataclass
class _Beat:
    pb_id: str
    kind: str
    side: str
    start_t: float
    end_t: float


def clock_minute(period: int, t: float, period_two_start: float) -> float:
    """Match-clock minute: period 2 restarts at 45 after any period 1 stoppage."""
    return t / 60.0 if period == 1 else 45.0 + (t - period_two_start) / 60.0


class _Engine:
    def __init__(self, brief: MatchBrief) -> None:
        self.brief = brief
        self.rng = random.Random(brief.seed)
        bias = STORY_POSSESSION.get(brief.storyline.id.value, (1.0, 1.0))
        self.teams: dict[str, _Team] = {}
        for side, team, w in (
            ("home", brief.home, bias[0]),
            ("away", brief.away, bias[1]),
        ):
            self.teams[side] = _Team(
                side,
                team.formation.value,
                team.press.root,
                team.directness.root,
                team.line_height.root,
                w,
            )
        self.t = 0.0
        self.period = 1
        self.seq = 0
        self.poss = "home"
        self.poss_id = 0
        self.ball: Pt = (60.0, 40.0)
        self.holder = 10
        self.pressured = False
        self.out: list[dict[str, Any]] = []
        self.counts: dict[tuple[str, str], int] = {}
        self.xg_total = {"home": 0.0, "away": 0.0}
        self.shot_target = {
            side: SHOT_TARGET
            + sum(
                PENALTY_EXTRA_SHOTS
                for pb in brief.planted_beats
                if pb.side.value == side and pb.kind.value == "penalty"
            )
            for side in ("home", "away")
        }
        self.xg_target = {
            side: max(
                XG_TARGET
                - sum(
                    PENALTY_XG if pb.kind.value == "penalty" else PLANTED_XG_GUESS
                    for pb in brief.planted_beats
                    if pb.side.value == side and pb.kind.value != "red_card"
                ),
                XG_ORGANIC_MIN,
            )
            for side in ("home", "away")
        }
        self.p2_start = 0.0

    # ---- emission ----------------------------------------------------------------------------
    def _emit(
        self,
        type_: str,
        side: str,
        slot: int | None,
        loc: Pt,
        *,
        dt: float | None = None,
        end: Pt | None = None,
        outcome: str | None = None,
        beat: str | None = None,
        extra: dict[str, Any] | None = None,
        under_pressure: bool | None = None,
        possession: bool = True,
    ) -> None:
        lo, hi = EVENT_DT.get(type_, (0.0, 0.0))
        self.t += dt if dt is not None else self.rng.uniform(lo, hi)
        self.seq += 1
        if beat is None and type_ in ("shot", "foul", "corner"):
            self.counts[(side, type_)] = self.counts.get((side, type_), 0) + 1
        if beat is None and type_ == "shot" and extra and "shot" in extra:
            self.xg_total[side] += extra["shot"]["xg"]
        e: dict[str, Any] = {
            "id": f"ev-{self.seq:06d}",
            "match_id": self.brief.match_id,
            "seq": self.seq - 1,
            "period": self.period,
            "t": round(self.t, 2),
            "side": side,
            "type": type_,
            "location": [round(loc[0], 1), round(loc[1], 1)],
        }
        if possession:
            e["possession_id"] = self.poss_id
        if slot is not None:
            e["player_id"] = f"{side}-{slot + 1:02d}"
        if end is not None:
            e["end_location"] = [round(end[0], 1), round(end[1], 1)]
        if outcome is not None:
            e["outcome"] = outcome
        if under_pressure:
            e["under_pressure"] = True
        if beat is not None:
            e["planted_beat_id"] = beat
        if extra:
            e.update(extra)
        self.out.append(e)

    def _pace(self, side: str, kind: str, target: float) -> float:
        """Multiplier for the chance of an event, from how the team's count compares with its target."""
        expected = target * min(self.t / MATCH_SECONDS_GUIDE, 1.0)
        actual = (
            self.xg_total[side] if kind == "xg" else self.counts.get((side, kind), 0)
        )
        spread = XG_PACE_SCALE if kind == "xg" else math.sqrt(max(expected, PACE_FLOOR))
        behind = (expected - actual) / spread
        gain = XG_PACE_GAIN if kind == "xg" else PACE_GAIN
        return _clamp(math.exp(gain * behind), *PACE_RANGE)

    def _drain(self) -> Iterator[Event]:
        out, self.out = self.out, []
        for e in out:
            yield Event.model_validate(e)

    # ---- possession helpers ----------------------------------------------------------------------
    def _give(self, side: str, loc: Pt, slot: int) -> None:
        """Hand possession to a side at a location with a named holder."""
        if side != self.poss:
            self.poss = side
            self.poss_id += 1
        self.ball = loc
        self.holder = slot
        self.pressured = False

    def _pos_rel(self, team: _Team, slot: int, ball_rel: Pt) -> Pt:
        """Where a slot stands in its team's frame, from the shared shape model."""
        return shape.target(
            team.formation, slot, team.line_height, ball_rel, team.side == self.poss
        )

    def _nearest(
        self,
        team: _Team,
        loc_abs: Pt,
        roles: tuple[str, ...] = ("def", "mid", "att"),
        exclude: int = -1,
    ) -> int:
        """A slot near a location, weighted by distance and role."""
        ball_rel = to_rel(team.side, loc_abs)
        slots = [s for s in team.slots_with(*roles) if s != exclude] or [
            s for s in team.active if s != exclude
        ]
        w = [
            ROLE_ACTOR_W[team.role(s)]
            * math.exp(
                -((_dist(self._pos_rel(team, s, ball_rel), ball_rel) / PICK_SCALE) ** 2)
            )
            for s in slots
        ]
        return self.rng.choices(slots, weights=w)[0]

    def _keeper_ok(self, team: _Team, loc_abs: Pt) -> tuple[str, ...]:
        return (
            ("gk", "def", "mid", "att")
            if to_rel(team.side, loc_abs)[0] < 22.0
            else ("def", "mid", "att")
        )

    # ---- the natural step --------------------------------------------------------------------
    def _step(self) -> None:
        p, d = self.teams[self.poss], self.teams[_opp(self.poss)]
        if self._defend(p, d):
            return
        self._act(p, d)

    def _defend(self, p: _Team, d: _Team) -> bool:
        """The defending side may press. Returns True when that ended the possession or stopped play."""
        d_own = to_rel(d.side, self.ball)[0]
        engage_depth = ENGAGE_DEEP + (ENGAGE_HIGH - ENGAGE_DEEP) * d.line_height
        z = 1.0 / (1.0 + math.exp(-(d_own - engage_depth) / ENGAGE_SOFTNESS))
        if d_own < BOX_ENGAGE_DEPTH:
            z = max(z, BOX_ENGAGE_Z)
        if self.rng.random() >= PRESS_BASE + PRESS_GAIN * d.press * z:
            self.pressured = False
            return False
        slot = self._nearest(d, self.ball, ("def", "mid", "att"))
        committed = self.rng.randint(1, 1 + round((UNDER_PRESSURE_MAX - 1) * d.press))
        self._emit(
            "pressure",
            d.side,
            slot,
            self.ball,
            extra={"pressure": {"players_committed": committed}},
        )
        self.pressured = True
        ratio = d.weight / p.weight
        r = self.rng.random()
        p_tackle = (TACKLE_BASE + TACKLE_GAIN * d.press) * ratio
        if r < p_tackle:
            self._give(d.side, self.ball, slot)
            self._emit("tackle", d.side, slot, self.ball, outcome="won")
            self._maybe_clear(d)
            return True
        r -= p_tackle
        if r < DUEL_P:
            won = self.rng.random() < DUEL_WIN * ratio / (
                1.0 + DUEL_WIN * (ratio - 1.0)
            )
            if won:
                self._give(d.side, self.ball, slot)
            self._emit(
                "duel", d.side, slot, self.ball, outcome="won" if won else "lost"
            )
            if won:
                self._maybe_clear(d)
            return won
        r -= DUEL_P
        near_own_goal = to_rel(d.side, self.ball)[0] < BOX_ENGAGE_DEPTH
        if r < FOUL_P * self._pace(d.side, "foul", FOUL_TARGET) * (
            FOUL_BOX_FACTOR if near_own_goal else 1.0
        ):
            self._foul(p, d, slot)
            return True
        return False

    def _maybe_clear(self, winner: _Team) -> None:
        """A side that wins the ball close to its own goal may clear it."""
        if (
            to_rel(winner.side, self.ball)[0] < CLEAR_DEPTH
            and self.rng.random() < CLEAR_P
        ):
            self._clear(winner)

    def _clear(self, team: _Team) -> None:
        slot = (
            self.holder
            if team.role(self.holder) != "att"
            else self._nearest(team, self.ball, ("def",))
        )
        u, v = to_rel(team.side, self.ball)
        end = to_abs(
            team.side,
            (
                _clamp(u + self.rng.uniform(25, 45), 5, 115),
                _clamp(v + self.rng.gauss(0, 14), 3, 77),
            ),
        )
        self._emit("clearance", team.side, slot, self.ball, end=end)
        other = self.teams[_opp(team.side)]
        if self.rng.random() < CLEAR_LOSS:
            self._give(
                other.side, end, self._nearest(other, end, self._keeper_ok(other, end))
            )
        else:
            self._give(team.side, end, self._nearest(team, end))

    def _foul(self, p: _Team, d: _Team, slot: int) -> None:
        self._emit("foul", d.side, slot, self.ball)
        if slot not in d.yellows and self.rng.random() < YELLOW_P:
            d.yellows.add(slot)
            self._emit("card", d.side, slot, self.ball, outcome="yellow")
        self._free_kick(p, self.ball)

    def _free_kick(self, team: _Team, loc: Pt) -> None:
        slot = self._nearest(team, loc, ("mid", "att"))
        self._give(team.side, loc, slot)
        self._emit("free_kick", team.side, slot, loc)
        if (
            distance_to_goal(team.side, loc) < FREE_KICK_RANGE
            and self.rng.random() < FREE_KICK_SHOT_P
        ):
            self._shoot(team, slot, loc, header=False)

    def _act(self, p: _Team, d: _Team) -> None:
        u, v = to_rel(p.side, self.ball)
        dist_goal = math.hypot(120.0 - u, 40.0 - v)
        if p.role(self.holder) == "gk":
            self._pass(p, d)
            return
        w_shot = (
            SHOT_W
            * math.exp(-dist_goal / SHOT_DECAY)
            * self._pace(p.side, "shot", self.shot_target[p.side])
            * self._pace(p.side, "xg", self.xg_target[p.side])
            if dist_goal <= SHOT_RANGE
            else 0.0
        )
        w_carry = (
            CARRY_W * (1.2 - 0.6 * p.directness) * (0.4 if self.pressured else 1.0)
        )
        pick = self.rng.choices(
            ["pass", "carry", "shot"], weights=[PASS_W, w_carry, w_shot]
        )[0]
        if pick == "shot":
            self._shoot(p, self.holder, self.ball, header=self.rng.random() < 0.18)
        elif pick == "carry":
            self._carry(p)
        else:
            self._pass(p, d)

    def _carry(self, p: _Team) -> None:
        u, v = to_rel(p.side, self.ball)
        end_rel = (
            _clamp(u + self.rng.uniform(*CARRY_LEN), 2, 118),
            _clamp(v + self.rng.gauss(0, 5), 2, 78),
        )
        end = to_abs(p.side, end_rel)
        self._emit(
            "carry",
            p.side,
            self.holder,
            self.ball,
            end=end,
            under_pressure=self.pressured,
        )
        self.ball = end

    # ---- passing ------------------------------------------------------------------------------
    def _choose_recipient(self, p: _Team) -> tuple[int, Pt]:
        ball_rel = to_rel(p.side, self.ball)
        desired = PASS_LEN_PATIENT + (PASS_LEN_DIRECT - PASS_LEN_PATIENT) * p.directness
        fwd = FWD_BASE + FWD_GAIN * p.directness
        slots: list[int] = []
        weights: list[float] = []
        positions: dict[int, Pt] = {}
        for s in sorted(p.active):
            if s == self.holder:
                continue
            pos = self._pos_rel(p, s, ball_rel)
            d = _dist(pos, ball_rel)
            if d < MIN_PASS:
                continue
            positions[s] = pos
            slots.append(s)
            weights.append(
                ROLE_RECEIVE_W[p.role(s)]
                * math.exp(-(((d - desired) / PASS_SPREAD) ** 2))
                * math.exp(fwd * (pos[0] - ball_rel[0]) / d)
            )
        slot = self.rng.choices(slots, weights=weights)[0]
        return slot, positions[slot]

    def _pass_fields(
        self, p: _Team, start: Pt, end: Pt, pressured: bool
    ) -> tuple[dict[str, Any], float]:
        """Quality fields for a pass and its completion probability."""
        length = _dist(start, end)
        high_p = _clamp(
            HIGH_BASE
            + HIGH_DIRECTNESS * p.directness
            + HIGH_LENGTH * max(0.0, length - 20.0),
            0.0,
            0.9,
        )
        r = self.rng.random()
        height = (
            "high"
            if r < high_p
            else ("low" if r < high_p + (1 - high_p) * LOW_SHARE else "ground")
        )
        difficulty = _clamp(
            DIFF_BASE
            + DIFF_LENGTH * length
            + (DIFF_PRESSURE if pressured else 0.0)
            + (DIFF_HIGH if height == "high" else 0.0)
            + self.rng.uniform(-0.05, 0.05),
            0.0,
            1.0,
        )
        lo, hi = SPEED_RANGE[height]
        speed = _clamp(
            lo
            + (hi - lo) * min(length / SPEED_FULL_LEN, 1.0)
            + self.rng.uniform(-1.2, 1.2),
            lo,
            hi,
        )
        fields = {
            "length_m": round(length, 1),
            "progressive": is_progressive(p.side, start, end),
            "height": height,
            "difficulty": round(difficulty, 3),
            "speed_ms": round(speed, 1),
        }
        p_complete = _clamp(
            COMPLETE_MAX
            - COMPLETE_SLOPE * difficulty
            - COMPLETE_DIRECTNESS * (p.directness - 0.5),
            0.05,
            0.99,
        )
        return fields, p_complete

    def _pass(self, p: _Team, d: _Team) -> None:
        slot, pos = self._choose_recipient(p)
        ball_rel = to_rel(p.side, self.ball)
        come = self.rng.uniform(
            0.0, PASS_COME_SHORT
        )  # the receiver comes toward the ball
        end_rel = (
            _clamp(
                pos[0] + come * (ball_rel[0] - pos[0]) + self.rng.gauss(0, 2.5), 1, 119
            ),
            _clamp(
                pos[1] + come * (ball_rel[1] - pos[1]) + self.rng.gauss(0, 2.5), 1, 79
            ),
        )
        end = to_abs(p.side, end_rel)
        fields, p_complete = self._pass_fields(p, self.ball, end, self.pressured)
        complete = self.rng.random() < p_complete
        fields["recipient_id"] = f"{p.side}-{slot + 1:02d}"
        self._emit(
            "pass",
            p.side,
            self.holder,
            self.ball,
            end=end,
            outcome="complete" if complete else "incomplete",
            extra={"pass": fields},
            under_pressure=self.pressured,
        )
        if complete:
            self._give(p.side, end, slot)
            return
        self._lost_pass(p, d, end, slot)

    def _lost_pass(self, p: _Team, d: _Team, end: Pt, slot: int) -> None:
        if to_rel(p.side, end)[
            0
        ] >= BOX_U and self.rng.random() < CORNER_AFTER_BOX_LOSS * self._pace(
            p.side, "corner", CORNER_TARGET
        ):
            self._corner(p)
            return
        r = self.rng.random()
        if r < INTERCEPT_SHARE:
            who = self._nearest(d, end, self._keeper_ok(d, end))
            self._give(d.side, end, who)
            self._emit("interception", d.side, who, end, outcome="won")
            self._maybe_clear(d)
        elif r < INTERCEPT_SHARE + OUT_SHARE:
            if to_rel(p.side, end)[0] >= GOAL_LINE_U:
                if self.rng.random() < CORNER_AFTER_DEFLECT * self._pace(
                    p.side, "corner", CORNER_TARGET
                ):
                    self._corner(p)
                else:
                    self._goal_kick(d)
            else:
                edge = (end[0], 0.5 if end[1] < 40 else 79.5)
                who = self._nearest(d, edge, ("def", "mid"))
                self._give(d.side, edge, who)
                self._emit("throw_in", d.side, who, edge)
        elif self.rng.random() < d.weight / (d.weight + p.weight):
            self._give(d.side, end, self._nearest(d, end, self._keeper_ok(d, end)))
            self._maybe_clear(d)
        else:
            self._give(p.side, end, slot)

    def _goal_kick(self, team: _Team) -> None:
        loc = to_abs(team.side, (6.0, 40.0))
        self._give(team.side, loc, 0)
        self._emit("goal_kick", team.side, 0, loc)

    # ---- shooting -----------------------------------------------------------------------------
    def _shoot(
        self,
        team: _Team,
        slot: int,
        loc: Pt,
        *,
        header: bool,
        beat: str | None = None,
        goal: bool = False,
        xg: float | None = None,
        dt: float | None = None,
    ) -> None:
        if xg is not None:
            xg_val = xg
        elif goal:
            xg_val = max(shot_xg(team.side, loc, header), PLANTED_XG_MIN)
        else:
            xg_val = min(shot_xg(team.side, loc, header), ORGANIC_XG_MAX)
        lo, hi = HEADER_SPEED if header else FOOT_SPEED
        body = "head" if header else self.rng.choice(["right_foot", "left_foot"])
        opp = self.teams[_opp(team.side)]
        if goal:
            outcome = "goal"
        else:
            weights = (
                SCORING_OUTCOMES if self.rng.random() < xg_val else MISSING_OUTCOMES
            )
            outcome = self.rng.choices(
                ["saved", "wide", "blocked", "post"], weights=weights
            )[0]
        self._emit(
            "shot",
            team.side,
            slot,
            loc,
            dt=dt,
            end=to_abs(team.side, (120.0, _clamp(40.0 + self.rng.gauss(0, 7), 33, 47))),
            outcome=outcome,
            beat=beat,
            extra={
                "shot": {
                    "xg": round(xg_val, 3),
                    "body_part": body,
                    "speed_ms": round(self.rng.uniform(lo, hi), 1),
                }
            },
            under_pressure=self.pressured,
        )
        self.pressured = False
        if outcome == "goal":
            self._kick_off(opp)
        elif outcome == "saved":
            if self.rng.random() < CORNER_AFTER_SAVE * self._pace(
                team.side, "corner", CORNER_TARGET
            ):
                self._corner(team)
            else:
                self._give(opp.side, to_abs(opp.side, (8.0, 40.0)), 0)
        elif outcome == "wide":
            if self.rng.random() < CORNER_AFTER_WIDE * self._pace(
                team.side, "corner", CORNER_TARGET
            ):
                self._corner(team)
            else:
                self._goal_kick(opp)
        elif outcome == "blocked":
            if self.rng.random() < CORNER_AFTER_BLOCK * self._pace(
                team.side, "corner", CORNER_TARGET
            ):
                self._corner(team)
            else:
                self._give(opp.side, loc, self._nearest(opp, loc))
        elif self.rng.random() < REBOUND_AFTER_POST:
            self._give(team.side, loc, self._nearest(team, loc, ("mid", "att")))
        else:
            self._give(opp.side, loc, self._nearest(opp, loc, ("def",)))
            self._clear(opp)

    def _corner(self, team: _Team, beat: str | None = None) -> None:
        loc = to_abs(team.side, (120.0, self.rng.choice([0.5, 79.5])))
        taker = self._nearest(team, loc, ("mid", "att"))
        self._give(team.side, loc, taker)
        self._emit("corner", team.side, taker, loc, beat=beat)
        if beat is not None:
            return
        if self.rng.random() < CORNER_SHOT_P:
            shooter = self._nearest(
                team, to_abs(team.side, (112.0, 40.0)), ("def", "att")
            )
            at = to_abs(
                team.side, (self.rng.uniform(106, 114), self.rng.uniform(30, 50))
            )
            self._shoot(team, shooter, at, header=True)
        else:
            opp = self.teams[_opp(team.side)]
            self._give(
                opp.side,
                to_abs(opp.side, (10.0, 40.0)),
                self._nearest(opp, loc, ("def",)),
            )
            self._clear(opp)

    def _kick_off(self, team: _Team, dt: float | None = None) -> None:
        slot = max(team.slots_with("att") or [10])
        self._give(team.side, (60.0, 40.0), slot)
        self._emit("kick_off", team.side, slot, (60.0, 40.0), dt=dt)

    # ---- planted beats ------------------------------------------------------------------------
    def _scripted_pass(
        self,
        p: _Team,
        passer: int,
        recipient: int,
        start: Pt,
        end: Pt,
        beat: str,
        dt: float,
    ) -> None:
        fields, _ = self._pass_fields(p, start, end, False)
        fields["recipient_id"] = f"{p.side}-{recipient + 1:02d}"
        self._emit(
            "pass",
            p.side,
            passer,
            start,
            dt=dt,
            end=end,
            outcome="complete",
            beat=beat,
            extra={"pass": fields},
        )

    def _split(self, total: float, n: int) -> list[float]:
        parts = [self.rng.uniform(0.7, 1.3) for _ in range(n)]
        s = sum(parts)
        return [total * x / s for x in parts]

    def _run_beat(self, b: _Beat) -> None:
        self.t = max(self.t, b.start_t)
        getattr(self, f"_seq_{b.kind}")(self.teams[b.side], b.pb_id)

    def _seq_counter_goal(self, s: _Team, beat: str) -> None:
        rel = to_rel(s.side, self.ball)
        start_rel = (
            rel
            if 22.0 <= rel[0] <= 52.0
            else (self.rng.uniform(25, 50), self.rng.uniform(15, 65))
        )
        total = self.rng.uniform(*COUNTER_SECONDS)
        n_pass = self.rng.choice([1, 2])
        shot_rel = (self.rng.uniform(106, 113), self.rng.uniform(32, 48))
        carry_end = (
            start_rel[0] + self.rng.uniform(14, 22),
            _clamp(start_rel[1] + self.rng.gauss(0, 4), 8, 72),
        )
        legs = [carry_end]
        for i in range(1, n_pass + 1):
            f = i / n_pass
            legs.append(
                (
                    carry_end[0] + (shot_rel[0] - carry_end[0]) * f,
                    carry_end[1] + (shot_rel[1] - carry_end[1]) * f,
                )
            )
        dts = self._split(total, 1 + n_pass + 1)
        first = self._nearest(s, to_abs(s.side, start_rel), ("def", "mid"))
        self._give(s.side, to_abs(s.side, start_rel), first)
        self._emit(
            "interception",
            s.side,
            first,
            to_abs(s.side, start_rel),
            dt=self.rng.uniform(0.8, 1.6),
            outcome="won",
            beat=beat,
        )
        self._emit(
            "carry",
            s.side,
            first,
            to_abs(s.side, start_rel),
            dt=dts[0],
            end=to_abs(s.side, carry_end),
            beat=beat,
        )
        passer, here = first, carry_end
        for i in range(n_pass):
            last = i == n_pass - 1
            rec = self._nearest(
                s,
                to_abs(s.side, legs[i + 1]),
                ("att",) if last else ("mid", "att"),
                exclude=passer,
            )
            self._scripted_pass(
                s,
                passer,
                rec,
                to_abs(s.side, here),
                to_abs(s.side, legs[i + 1]),
                beat,
                dts[i + 1],
            )
            passer, here = rec, legs[i + 1]
        self._shoot(
            s,
            passer,
            to_abs(s.side, here),
            header=False,
            beat=beat,
            goal=True,
            dt=dts[-1],
        )

    def _seq_set_piece_goal(self, s: _Team, beat: str) -> None:
        self._corner(s, beat=beat)
        shooter = self._nearest(s, to_abs(s.side, (112.0, 40.0)), ("def", "att"))
        at = to_abs(s.side, (self.rng.uniform(106, 114), self.rng.uniform(32, 48)))
        self._shoot(
            s,
            shooter,
            at,
            header=True,
            beat=beat,
            goal=True,
            dt=self.rng.uniform(*SET_PIECE_SECONDS),
        )

    def _seq_high_turnover_goal(self, s: _Team, beat: str) -> None:
        o = self.teams[_opp(s.side)]
        while True:
            loc_rel = (self.rng.uniform(84, 106), self.rng.uniform(14, 66))
            if math.hypot(120 - loc_rel[0], 40 - loc_rel[1]) <= TURNOVER_MAX_DIST:
                break
        loc = to_abs(s.side, loc_rel)
        dts = self._split(self.rng.uniform(*TURNOVER_SECONDS), 4)
        presser = self._nearest(s, loc, ("mid", "att"))
        winner = self._nearest(s, loc, ("mid", "att"), exclude=presser)
        self._give(o.side, loc, self._nearest(o, loc))
        self._emit(
            "pressure",
            s.side,
            presser,
            loc,
            dt=self.rng.uniform(0.6, 1.4),
            beat=beat,
            extra={"pressure": {"players_committed": self.rng.randint(2, 3)}},
            possession=True,
        )
        self._give(s.side, loc, winner)
        self._emit(
            "interception", s.side, winner, loc, dt=dts[0], outcome="won", beat=beat
        )
        end_rel = (
            _clamp(loc_rel[0] + self.rng.uniform(2, 8), 96, 113),
            self.rng.uniform(30, 50),
        )
        rec = self._nearest(s, to_abs(s.side, end_rel), ("att",), exclude=winner)
        self._scripted_pass(s, winner, rec, loc, to_abs(s.side, end_rel), beat, dts[1])
        self._give(s.side, to_abs(s.side, end_rel), rec)
        self._shoot(
            s,
            rec,
            to_abs(s.side, end_rel),
            header=False,
            beat=beat,
            goal=True,
            dt=dts[2] + dts[3],
        )

    def _seq_open_play_goal(self, s: _Team, beat: str) -> None:
        n = self.rng.randint(3, 6)
        u0, uf = self.rng.uniform(38, 66), self.rng.uniform(104, 112)
        pts: list[Pt] = [
            (
                u0 + (uf - u0) * i / n,
                _clamp(
                    self.rng.uniform(14, 66) if i < n else self.rng.uniform(28, 52),
                    4,
                    76,
                ),
            )
            for i in range(n + 1)
        ]
        slots = [self._nearest(s, to_abs(s.side, pts[0]), ("def", "mid"))]
        for i in range(1, n + 1):
            slots.append(
                self._nearest(
                    s,
                    to_abs(s.side, pts[i]),
                    ("att",) if i == n else ("mid", "att"),
                    exclude=slots[-1],
                )
            )
        self._give(s.side, to_abs(s.side, pts[0]), slots[0])
        for i in range(n):
            self._scripted_pass(
                s,
                slots[i],
                slots[i + 1],
                to_abs(s.side, pts[i]),
                to_abs(s.side, pts[i + 1]),
                beat,
                self.rng.uniform(*OPEN_PLAY_PASS_DT),
            )
        self._shoot(
            s,
            slots[n],
            to_abs(s.side, pts[n]),
            header=False,
            beat=beat,
            goal=True,
            dt=self.rng.uniform(1.5, 2.5),
        )

    def _seq_red_card(self, s: _Team, beat: str) -> None:
        o = self.teams[_opp(s.side)]
        loc = self.ball
        slot = self._nearest(s, loc, ("def", "mid"))
        self._give(o.side, loc, self._nearest(o, loc))
        self._emit("foul", s.side, slot, loc, dt=self.rng.uniform(0.8, 2.0), beat=beat)
        self._emit("card", s.side, slot, loc, outcome="red", beat=beat)
        s.active.discard(slot)
        s.weight *= RED_CARD_WEIGHT
        self._free_kick(o, loc)

    def _seq_penalty(self, s: _Team, beat: str) -> None:
        o = self.teams[_opp(s.side)]
        foul_rel = (self.rng.uniform(106, 116), self.rng.uniform(26, 54))
        foul_loc = to_abs(s.side, foul_rel)
        fouler = self._nearest(o, foul_loc, ("def",))
        self._give(s.side, foul_loc, self._nearest(s, foul_loc, ("att",)))
        self._emit(
            "foul", o.side, fouler, foul_loc, dt=self.rng.uniform(0.8, 2.0), beat=beat
        )
        taker = max(s.slots_with("att"))
        self._shoot(
            s,
            taker,
            to_abs(s.side, (108.0, 40.0)),
            header=False,
            beat=beat,
            goal=True,
            xg=PENALTY_XG,
            dt=self.rng.uniform(*PENALTY_DELAY),
        )

    # ---- periods ------------------------------------------------------------------------------
    def _schedule(
        self, period: int, p_start: float, nominal_end: float
    ) -> tuple[list[_Beat], float]:
        """Place this period's planted beats at random times inside their windows."""
        beats: list[_Beat] = []
        for pb in self.brief.planted_beats:
            in_p1 = pb.minute_to <= 45
            if (period == 1) != in_p1:
                continue
            origin = p_start if period == 1 else self.p2_start
            base = 0.0 if period == 1 else 45.0
            lo = origin + (pb.minute_from - base) * 60.0
            hi = origin + (pb.minute_to - base) * 60.0
            dur = BEAT_MAX_SECONDS[pb.kind.value]
            start = self.rng.uniform(lo, max(lo, hi - dur - BEAT_MARGIN_S))
            beats.append(_Beat(pb.id, pb.kind.value, pb.side.value, start, start + dur))
        beats.sort(key=lambda b: b.start_t)
        end = max([nominal_end] + [b.end_t + PERIOD_TAIL_S for b in beats])
        return beats, end

    def run(self) -> Iterator[Event]:
        stop1 = self.rng.randint(*P1_STOPPAGE_MIN)
        stop2 = self.rng.randint(*P2_STOPPAGE_MIN)
        yield from self._run_period_lazily(1, 0.0, HALF_SECONDS + 60.0 * stop1, "home")
        self.p2_start = self.t
        yield from self._run_period_lazily(
            2, self.t, self.t + HALF_SECONDS + 60.0 * stop2, "away"
        )

    def _run_period_lazily(
        self, period: int, start_t: float, nominal_end: float, kicker: str
    ) -> Iterator[Event]:
        self.period = period
        self.t = start_t
        beats, end_t = self._schedule(period, start_t, nominal_end)
        self._emit("period_start", "home", None, (60.0, 40.0), dt=0.0, possession=False)
        self._kick_off(self.teams[kicker], dt=0.0)
        yield from self._drain()
        pending = list(beats)
        while self.t < end_t:
            if pending and pending[0].start_t <= self.t:
                self._run_beat(pending.pop(0))
            else:
                self._step()
            yield from self._drain()
        self._emit("period_end", "home", None, self.ball, dt=0.0, possession=False)
        yield from self._drain()
