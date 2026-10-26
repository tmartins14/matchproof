"""Player positions, version 1: all 22 players at 5 Hz plus a freeze frame for every event (ADR 0005).

Players steer toward their shape target (shape.py) under a speed and an acceleration cap. The actor of
each event is steered to the event location and snapped onto it at the event's time; a pass recipient is
steered to the pass end by the next event. Everyone else keeps following the shape model.

Offside: the side in possession is held level with or behind the second-last defender (or the ball, if
that is further forward) until the pass that releases a player is played; the intended recipient of a
pass then runs onto it. The engine is not told: events never read this layer.
"""

import math
from collections import deque
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any, Literal

from contracts.models import Event, MatchBrief, PositionFrame

from . import iter_events, shape

Pt = tuple[float, float]

FRAME_DT = 0.2  # seconds between frames (5 Hz)
MAX_SPEED_V1 = 9.5  # reported speed cap for every player, m/s
MAX_ACCEL = 5.0  # m/s^2 the players accelerate at; the measured cap is 6 (sim.realism) once 0.1 m rounding is allowed for
BRAKE = 5.0  # m/s^2 a player brakes at when settling on a target
EDGE_BRAKE = 1.5  # m/s^2 assumed when slowing for a touchline or goal line
EDGE_INSET_M = 0.5
SEPARATION_M = 3.5  # teammates closer than this aim apart
SEPARATION_GAIN = (
    1.5  # m/s of velocity away from a teammate per metre closer than SEPARATION_M
)
SEPARATION_MAX_MS = 2.5  # the most velocity a nudge adds
SNAP_KEEPS = 0.0  # share of its velocity an event actor keeps when placed on the event
OFFSIDE_MARGIN_M = 0.8  # the possessing side stays this far inside the offside line
HALF_X = 60.0
ROUNDING_MARGIN_MS = (
    0.7  # movement stays this far under the cap so 0.1 m rounding cannot break it
)
SPEED_GAIN = (
    2.0  # per second: how sharply a player closes on a target (time constant 0.5 s)
)
COMMIT_SLACK = 1.6  # a pinned player leaves the shape this many times the travel time before the event
COMMIT_LEAD_S = 0.4  # extra seconds of lead before a pinned event
LOOKAHEAD = 3  # how many upcoming events' actors start steering early; the stream trails by this many events
GOAL_RESET_S = (
    6.0  # seconds after a goal before the ball and shape return to the kick-off set-up
)
BALL_CARRY_MIN_S = 0.2  # shortest time the ball takes to follow an event's path
KICK_OFF_POINT: Pt = (60.0, 40.0)
# Event types after which the acting side has the ball; others leave possession unchanged.
POSSESSION_TYPES = frozenset(
    {
        "pass",
        "carry",
        "shot",
        "kick_off",
        "corner",
        "free_kick",
        "throw_in",
        "goal_kick",
        "clearance",
    }
)
# Event types that win the ball for the acting side when the outcome is "won".
WINNING_TYPES = frozenset({"tackle", "interception", "duel"})


def freeze_source_id(event_id: str) -> str:
    """Source id for facts drawn from an event's freeze frame: ff- plus the event's six digits."""
    return "ff-" + event_id.removeprefix("ev-")


@dataclass
class _Player:
    side: str
    slot: int
    id: str
    x: float
    y: float
    speed: float = 0.0
    active: bool = True
    commit: tuple[float, float, float] | None = None  # x, y, deadline
    vx: float = 0.0
    vy: float = 0.0
    free_until: float = (
        -1.0
    )  # a pass recipient may run beyond the offside line until then
    run_in: tuple[float, float, float] | None = (
        None  # pass end x, y and the time the pass is played
    )


@dataclass
class FrameStats:
    snaps: int = 0  # event actors placed on their event location
    large_snaps: int = 0  # snaps farther than a normal step allows
    reset_ticks: list[float] = field(
        default_factory=list
    )  # times everyone was reset to the kick-off shape


def travel_time(dist: float, cap: float) -> float:
    """Seconds to cover a distance from rest, accelerating at MAX_ACCEL up to the cap."""
    ramp = cap * cap / MAX_ACCEL
    if dist >= ramp:
        return dist / cap + cap / MAX_ACCEL
    return 2.0 * math.sqrt(dist / MAX_ACCEL)


def _turn_time(p: _Player, tx: float, ty: float) -> float:
    """Extra seconds to stop and turn when running away from a point."""
    d = math.hypot(tx - p.x, ty - p.y)
    if d < 1e-6:
        return 0.0
    toward = (p.vx * (tx - p.x) + p.vy * (ty - p.y)) / d
    return 2.0 * max(-toward, 0.0) / MAX_ACCEL


def _edge_limited(v: float, at: float, length: float) -> float:
    """A velocity along an axis of the pitch, cut to what can be braked before the edge."""
    room = (length - at) if v > 0 else at
    cap = math.sqrt(2.0 * EDGE_BRAKE * max(room - EDGE_INSET_M, 0.0))
    return math.copysign(min(abs(v), cap), v)


def _on_line(p: _Player, ex: float, ey: float, sign: float, bound: float) -> Pt:
    """Where the straight run from the player to the pass end meets the offside line."""
    s_p, s_e = sign * p.x, sign * ex
    if s_e <= bound:
        return (ex, ey)
    if s_p >= bound:
        return (sign * bound, ey)
    f = (bound - s_p) / (s_e - s_p)
    return (p.x + (ex - p.x) * f, p.y + (ey - p.y) * f)


class FrameSimulator:
    """Steps 22 players through a match's events and emits frames and freeze frames."""

    def __init__(self, brief: MatchBrief) -> None:
        self.brief = brief
        self.match_id = brief.match_id
        self.formations = {
            "home": brief.home.formation.value,
            "away": brief.away.formation.value,
        }
        self.line = {
            "home": brief.home.line_height.root,
            "away": brief.away.line_height.root,
        }
        self.press = {
            "home": brief.home.press.root,
            "away": brief.away.press.root,
        }
        self.goals = {"home": 0, "away": 0}
        self.down = {"home": 0, "away": 0}  # players sent off
        self.p2_start = 0.0
        self.step_cap = MAX_SPEED_V1 - ROUNDING_MARGIN_MS
        self.t = 0.0
        self.poss = "home"
        self.ball: Pt = KICK_OFF_POINT
        self.ball_seg: tuple[Pt, Pt, float, float] | None = (
            None  # start, end, t0, duration
        )
        self.players: dict[tuple[str, int], _Player] = {}
        self.stats = FrameStats()
        self._period = 1
        self.reset_at: float | None = None
        self.conceding: str | None = None
        self.holder: tuple[str, int] | None = (
            None  # the player with the ball, who is never offside
        )
        self.sent_off: list[
            _Player
        ] = []  # leave the frames once time moves past their card
        self._reset_shape()

    # ---- shape ---------------------------------------------------------------------------------
    def _shape_target(self, p: _Player) -> Pt:
        ball_rel = (
            (self.ball[0], self.ball[1])
            if p.side == "home"
            else (120.0 - self.ball[0], self.ball[1])
        )
        other = "away" if p.side == "home" else "home"
        minute = (
            self.t / 60.0
            if self._period == 1
            else 45.0 + (self.t - self.p2_start) / 60.0
        )
        state = shape.GameState(
            minute, self.goals[p.side] - self.goals[other], self.down[p.side]
        )
        u, v = shape.target(
            self.formations[p.side],
            p.slot,
            self.line[p.side],
            ball_rel,
            p.side == self.poss,
            state,
            self.press[p.side],
        )
        return (
            (u, v) if p.side == "home" else (120.0 - u, v)
        )  # unrounded, so steering stays smooth

    def _reset_shape(self) -> None:
        """Everyone to their shape target for a ball on the centre spot."""
        self.ball = KICK_OFF_POINT
        for side in ("home", "away"):
            for slot in range(11):
                key = (side, slot)
                p = self.players.get(key) or _Player(
                    side, slot, f"{side}-{slot + 1:02d}", 0.0, 0.0
                )
                self.players[key] = p
                if p.active:
                    p.x, p.y = self._shape_target(p)
                    p.speed = p.vx = p.vy = 0.0
                    p.commit = p.run_in = None
                    p.free_until = -1.0

    # ---- movement ------------------------------------------------------------------------------
    def _ball_at(self, t: float) -> Pt:
        if self.ball_seg is None:
            return self.ball
        (sx, sy), (ex, ey), t0, dur = self.ball_seg
        f = 1.0 if dur <= 0 else min(max((t - t0) / dur, 0.0), 1.0)
        return (sx + (ex - sx) * f, sy + (ey - sy) * f)

    def _advance(self, to_t: float) -> None:
        dt = to_t - self.t
        if dt <= 0:
            return
        for p in self.sent_off:
            p.active = False
        self.sent_off.clear()
        self.t = to_t
        self.ball = self._ball_at(to_t)
        if self.reset_at is not None and to_t >= self.reset_at:
            self.reset_at = None
            self.ball, self.ball_seg = KICK_OFF_POINT, None
            if self.conceding is not None:
                self.poss = self.conceding
        cap = self.step_cap
        sign = 1.0 if self.poss == "home" else -1.0
        limit = self._offside_limit(self.poss)
        plan: list[
            list[Any]
        ] = []  # player, target x, target y, seconds to arrive (or None)
        for p in self.players.values():
            if not p.active:
                continue
            bound = (
                limit
                if p.side == self.poss
                and (p.side, p.slot) != self.holder
                and to_t >= p.free_until
                else None
            )
            tx, ty = self._shape_target(p)
            arrive: float | None = None
            c = p.commit
            if c is not None and to_t >= c[2]:
                p.commit = c = None
            if p.run_in is not None and to_t >= p.run_in[2]:
                p.run_in = None
            if c is not None:
                remaining = c[2] - to_t
                dist_c = math.hypot(c[0] - p.x, c[1] - p.y)
                if (
                    remaining
                    <= (travel_time(dist_c, cap) + _turn_time(p, c[0], c[1]))
                    * COMMIT_SLACK
                    + COMMIT_LEAD_S
                ):
                    tx, ty = c[0], c[1]
                    arrive = max(remaining, dt)
            if bound is not None:
                if p.run_in is not None:
                    # Run onto the pass: be on the line the moment it is played, already at speed.
                    ex, ey, t_pass = p.run_in
                    gx, gy = _on_line(p, ex, ey, sign, bound)
                    remaining = t_pass - to_t
                    dist_g = math.hypot(gx - p.x, gy - p.y)
                    if (
                        remaining
                        <= travel_time(dist_g, cap) * COMMIT_SLACK + COMMIT_LEAD_S
                    ):
                        tx, ty, arrive = gx, gy, max(remaining, dt)
                if sign * tx > bound:
                    tx = sign * bound
            plan.append([p, tx, ty, arrive, 0.0, 0.0])
        self._keep_apart(plan)
        for p, tx, ty, arrive, pvx, pvy in plan:
            self._steer(p, tx, ty, dt, arrive, cap, pvx, pvy)

    @staticmethod
    def _keep_apart(plan: list[list[Any]]) -> None:
        """Teammates closer than SEPARATION_M are nudged apart: each is given a velocity away from the other."""
        for i, a in enumerate(plan):
            pa = a[0]
            for b in plan[i + 1 :]:
                pb = b[0]
                if pa.side != pb.side:
                    continue
                dx, dy = pa.x - pb.x, pa.y - pb.y
                if abs(dx) >= SEPARATION_M or abs(dy) >= SEPARATION_M:
                    continue
                d = math.hypot(dx, dy)
                if d >= SEPARATION_M:
                    continue
                ux, uy = (
                    (dx / d, dy / d)
                    if d > 1e-6
                    else (0.0, 1.0 if pa.slot < pb.slot else -1.0)
                )
                push = min((SEPARATION_M - d) * SEPARATION_GAIN, SEPARATION_MAX_MS)
                wa = (
                    0.5 if a[3] is not None else 1.0
                )  # a player arriving on time gives way less
                wb = 0.5 if b[3] is not None else 1.0
                a[4] += ux * push * wa
                a[5] += uy * push * wa
                b[4] -= ux * push * wb
                b[5] -= uy * push * wb

    def _steer(
        self,
        p: _Player,
        tx: float,
        ty: float,
        dt: float,
        arrive: float | None,
        cap: float,
        push_x: float = 0.0,
        push_y: float = 0.0,
    ) -> None:
        """Accelerate toward a point: reach it in `arrive` seconds if given, otherwise settle on it."""
        tx = min(
            max(tx, EDGE_INSET_M), 120.0 - EDGE_INSET_M
        )  # a run ends short of the line
        ty = min(max(ty, EDGE_INSET_M), 80.0 - EDGE_INSET_M)
        dx, dy = tx - p.x, ty - p.y
        dist = math.hypot(dx, dy)
        if dist < 1e-9:
            want_x = want_y = 0.0
        else:
            if arrive is not None:
                v = min(cap, dist / arrive)
            else:
                v = min(cap, dist * SPEED_GAIN, math.sqrt(2.0 * BRAKE * dist))
            want_x, want_y = dx / dist * v, dy / dist * v
        want_x, want_y = want_x + push_x, want_y + push_y
        w = math.hypot(want_x, want_y)
        if w > cap:
            want_x, want_y = want_x / w * cap, want_y / w * cap
        # Never run faster toward a pitch edge than the player could stop before it.
        want_x = _edge_limited(want_x, p.x, 120.0)
        want_y = _edge_limited(want_y, p.y, 80.0)
        dvx, dvy = want_x - p.vx, want_y - p.vy
        dv = math.hypot(dvx, dvy)
        limit = MAX_ACCEL * dt
        if dv > limit:
            dvx, dvy = dvx / dv * limit, dvy / dv * limit
        p.vx += dvx
        p.vy += dvy
        speed = math.hypot(p.vx, p.vy)
        if speed > cap:
            p.vx, p.vy, speed = p.vx / speed * cap, p.vy / speed * cap, cap
        p.x, p.y = p.x + p.vx * dt, p.y + p.vy * dt
        if not 0.0 <= p.x <= 120.0:  # against a goal line the run stops
            p.x, p.vx = min(max(p.x, 0.0), 120.0), 0.0
        if not 0.0 <= p.y <= 80.0:
            p.y, p.vy = min(max(p.y, 0.0), 80.0), 0.0
        speed = math.hypot(p.vx, p.vy)
        p.speed = speed

    def _offside_limit(self, side: str) -> float:
        """How far toward goal (signed x of the side's frame) an attacker without the ball may stand."""
        sign = 1.0 if side == "home" else -1.0
        theirs = sorted(
            (sign * q.x for q in self.players.values() if q.side != side and q.active),
            reverse=True,
        )
        second_last = theirs[1] if len(theirs) > 1 else sign * HALF_X
        return max(sign * self.ball[0], second_last, sign * HALF_X) - OFFSIDE_MARGIN_M

    # ---- events --------------------------------------------------------------------------------
    def _player(self, side: str, player_id: str) -> _Player:
        return self.players[(side, int(player_id.split("-")[1]) - 1)]

    def apply(self, e: Event, upcoming: list[Event]) -> None:
        """Pin the actor, start the ball path and set up steering for the next event."""
        loc = (e.location.root[0].root, e.location.root[1].root)
        end = (
            (e.end_location.root[0].root, e.end_location.root[1].root)
            if e.end_location
            else None
        )
        kind = e.type.value
        side = e.side.value
        if kind == "period_start" and e.period.value == 2:
            self._period = 2
            self.p2_start = e.t.root
            self._reset_shape()
            self.stats.reset_ticks.append(e.t.root)
        if kind in POSSESSION_TYPES or (
            kind in WINNING_TYPES and e.outcome is not None and e.outcome.value == "won"
        ):
            self.poss = side
        if e.player_id is not None:
            actor = self._player(side, e.player_id.root)
            if actor.active:
                moved = math.hypot(actor.x - loc[0], actor.y - loc[1])
                self.stats.snaps += 1
                if moved > self.step_cap * FRAME_DT + 0.05:
                    self.stats.large_snaps += 1
                actor.x, actor.y = loc
                # Placed, not run: the placement ends the run that led here (and so is never an acceleration).
                actor.vx = _edge_limited(actor.vx * SNAP_KEEPS, actor.x, 120.0)
                actor.vy = _edge_limited(actor.vy * SNAP_KEEPS, actor.y, 80.0)
                actor.commit = actor.run_in = None
                self.holder = None if kind == "pass" else (side, actor.slot)
            if kind == "card" and e.outcome is not None and e.outcome.value == "red":
                self.sent_off.append(actor)
                self.down[side] += 1
        self.ball = loc
        nxt = upcoming[0] if upcoming else None
        gap = (nxt.t.root - e.t.root) if nxt is not None else 0.0
        if kind == "shot" and e.outcome is not None and e.outcome.value == "goal":
            self.goals[side] += 1
            self.reset_at = e.t.root + GOAL_RESET_S
            self.conceding = "away" if side == "home" else "home"
        if end is None:
            self.ball_seg = None
        else:
            length = math.hypot(end[0] - loc[0], end[1] - loc[1])
            speed = 0.0
            if e.pass_ is not None and e.pass_.speed_ms:
                speed = e.pass_.speed_ms
            elif e.shot is not None and e.shot.speed_ms:
                speed = e.shot.speed_ms
            dur = length / speed if speed > 0 else gap
            if gap > 0:
                dur = min(dur, gap) if speed > 0 else gap
            self.ball_seg = (loc, end, e.t.root, max(dur, BALL_CARRY_MIN_S))
        if nxt is None:
            return
        # Steering for the next event: its actor to its location, a pass recipient or carrier to the end.
        if end is not None and e.player_id is not None:
            if kind == "carry":
                self._commit(self._player(side, e.player_id.root), end, nxt.t.root)
            elif e.pass_ is not None and e.pass_.recipient_id is not None:
                receiver = self._player(side, e.pass_.recipient_id.root)
                receiver.free_until = nxt.t.root
                receiver.run_in = None
                self._commit(receiver, end, nxt.t.root)
        for up in upcoming:
            if (
                up.type.value == "pass"
                and up.pass_ is not None
                and up.pass_.recipient_id is not None
                and up.end_location is not None
            ):
                r = self._player(up.side.value, up.pass_.recipient_id.root)
                if r.active and r.run_in is None:
                    r.run_in = (
                        up.end_location.root[0].root,
                        up.end_location.root[1].root,
                        up.t.root,
                    )
        for up in upcoming:
            if up.player_id is None:
                continue
            q = self._player(up.side.value, up.player_id.root)
            if q.commit is None:  # the earliest upcoming event wins
                self._commit(
                    q, (up.location.root[0].root, up.location.root[1].root), up.t.root
                )

    def _commit(self, p: _Player, at: Pt, deadline: float) -> None:
        if p.active:
            p.commit = (at[0], at[1], deadline)

    # ---- output --------------------------------------------------------------------------------
    def frame(self, t: float, freeze_of: str | None = None) -> PositionFrame:
        players: list[dict[str, Any]] = [
            {
                "id": p.id,
                "side": p.side,
                "at": [round(p.x, 1), round(p.y, 1)],
                "speed_ms": round(p.speed, 1),
                "role": "hold_slot",
            }
            for p in self.players.values()
            if p.active
        ]
        raw: dict[str, Any] = {
            "match_id": self.match_id,
            "t": round(t, 2),
            "ball": [round(self.ball[0], 1), round(self.ball[1], 1)],
            "possession": self.poss,
            "players": players,
        }
        if freeze_of is not None:
            raw["freeze_frame_of"] = freeze_of
        return PositionFrame.model_validate(raw)


Kind = Literal["event", "frame", "freeze"]


def run(
    brief: MatchBrief, events: Iterable[Event], sim: FrameSimulator | None = None
) -> Iterator[tuple[Kind, Event | None, PositionFrame | None]]:
    """The single pass behind every public iterator.

    Yields ("frame", None, frame) every 0.2 s, ("event", event, None) at each event and
    ("freeze", event, frame) straight after it. A frame that falls on an event's time follows the event.
    """
    sim = sim or FrameSimulator(brief)
    window: deque[Event] = deque()
    it = iter(events)
    tick = 0
    need = LOOKAHEAD + 1

    def tick_t(k: int) -> float:
        return round(k * FRAME_DT, 2)

    def fill() -> None:
        while len(window) < need:
            nxt = next(it, None)
            if nxt is None:
                return
            window.append(nxt)

    fill()
    while window:
        e = window.popleft()
        fill()
        while tick_t(tick) < e.t.root:
            sim._advance(tick_t(tick))
            yield "frame", None, sim.frame(tick_t(tick))
            tick += 1
        sim._advance(e.t.root)
        sim.apply(e, list(window)[:LOOKAHEAD])
        yield "event", e, None
        yield "freeze", e, sim.frame(e.t.root, freeze_of=e.id.root)
        same_time_follows = bool(window) and window[0].t.root == e.t.root
        if tick_t(tick) == e.t.root and not same_time_follows:
            yield "frame", None, sim.frame(e.t.root)
            tick += 1


def iter_frames(brief: MatchBrief, events: Iterable[Event]) -> Iterator[PositionFrame]:
    for kind, _, frame in run(brief, events):
        if kind == "frame" and frame is not None:
            yield frame


def iter_freeze_frames(
    brief: MatchBrief, events: Iterable[Event]
) -> Iterator[PositionFrame]:
    for kind, _, frame in run(brief, events):
        if kind == "freeze" and frame is not None:
            yield frame


def iter_stream(brief: MatchBrief) -> Iterator[Event | PositionFrame]:
    """Events and 5 Hz frames merged in time order; an event comes before a frame at the same time."""
    for kind, event, frame in run(brief, iter_events(brief)):
        if kind == "event" and event is not None:
            yield event
        elif kind == "frame" and frame is not None:
            yield frame
