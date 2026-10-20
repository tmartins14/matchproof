"""Player positions, version 1: all 22 players at 5 Hz plus a freeze frame for every event (ADR 0005).

Players steer toward their shape target (shape.py) under a speed cap. The actor of each event is
steered to the event location and snapped onto it at the event's time; a pass recipient is steered to
the pass end by the next event. Everyone else keeps following the shape model.
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
MAX_SPEED_V1 = 8.0  # reported speed cap for every player, m/s
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


@dataclass
class FrameStats:
    snaps: int = 0  # event actors placed on their event location
    large_snaps: int = 0  # snaps farther than a normal step allows
    reset_ticks: list[float] = field(
        default_factory=list
    )  # times everyone was reset to the kick-off shape


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
                    p.speed = 0.0
                    p.commit = None

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
        for p in self.players.values():
            if not p.active:
                continue
            tx, ty = self._shape_target(p)
            speed_limit = cap
            desired_gain = SPEED_GAIN
            c = p.commit
            if c is not None and to_t >= c[2]:
                p.commit = c = None
            if c is not None:
                remaining = c[2] - to_t
                dist_c = math.hypot(c[0] - p.x, c[1] - p.y)
                if remaining <= dist_c / cap * COMMIT_SLACK + COMMIT_LEAD_S:
                    tx, ty = c[0], c[1]
                    desired_gain = 1.0 / max(remaining, dt)
            dx, dy = tx - p.x, ty - p.y
            dist = math.hypot(dx, dy)
            if dist < 1e-9:
                p.speed = 0.0
                continue
            step = min(speed_limit, dist * desired_gain) * dt
            step = min(step, dist)
            p.x += dx / dist * step
            p.y += dy / dist * step
            p.speed = step / dt

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
                actor.commit = None
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
                self._commit(
                    self._player(side, e.pass_.recipient_id.root), end, nxt.t.root
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
