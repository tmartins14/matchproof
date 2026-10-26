"""Realism measures over events and 5 Hz frames: offside at the pass, speed, acceleration, overlap, line shape.

Pure functions over what the generator yields; nothing here feeds back into the engine or the frames.
All coordinates are the absolute pitch (120 x 80). The home team attacks toward x = 120 (ADR 0007).
"""

import math
from collections.abc import Iterable
from dataclasses import dataclass, field

from contracts.models import Event, PositionFrame

MAX_SPEED_MS = 9.5  # top speed a player may show between frames
MAX_ACCEL_MS2 = 6.0  # acceleration cap, measured over 0.6 s windows (see Motion)
ACCEL_STEPS = 3  # frames averaged into each velocity when measuring acceleration
FRAME_DT = 0.2  # seconds between frames (5 Hz), as in positions.py
OVERLAP_M = 1.5  # two teammates closer than this overlap
RESET_PLAYERS = (
    11  # this many players moving RESET_JUMP_M in one step is a restart, not running
)
RESET_JUMP_M = 3.0
HALF_X = 60.0
RESTART = "*"  # stands in `pinned` for every player at once
BACK_LINE = 4  # the four deepest outfielders of a side form its back line


@dataclass(frozen=True)
class Pos:
    id: str
    side: str
    x: float
    y: float


def positions(frame: PositionFrame) -> list[Pos]:
    return [
        Pos(p.id.root, p.side.value, p.at.root[0].root, p.at.root[1].root)
        for p in frame.players
    ]


def attack_sign(side: str) -> float:
    return 1.0 if side == "home" else -1.0


def is_offside(
    side: str, receiver: str, ball_x: float, players: Iterable[Pos]
) -> bool | None:
    """Is the receiver beyond the ball and the second-last defender, in the opponents' half?

    Level counts as onside. None when the receiver is not in the frame.
    """
    sign = attack_sign(side)
    others = [p for p in players if p.side != side]
    me = next((p for p in players if p.id == receiver), None)
    if me is None or len(others) < 2:
        return None
    toward = sorted((sign * p.x for p in others), reverse=True)
    second_last = toward[1]
    x = sign * me.x
    return x > sign * HALF_X and x > sign * ball_x and x > second_last


def forward_pass(e: Event) -> bool:
    if e.type.value != "pass" or e.end_location is None or e.pass_ is None:
        return False
    if e.pass_.recipient_id is None:
        return False
    sign = attack_sign(e.side.value)
    return sign * (e.end_location.root[0].root - e.location.root[0].root) > 0.0


def freeze_by_event(frames: Iterable[PositionFrame]) -> dict[str, PositionFrame]:
    return {f.freeze_frame_of.root: f for f in frames if f.freeze_frame_of is not None}


def offside_at_pass(
    frames: Iterable[PositionFrame], events: Iterable[Event]
) -> tuple[int, int]:
    """(offside forward passes, forward passes) judged on the freeze frame at each pass.

    Frames without freeze_frame_of are used by nearest time instead.
    """
    frames = list(frames)
    frozen = freeze_by_event(frames)
    plain = sorted((f for f in frames if f.freeze_frame_of is None), key=_t)
    off = total = 0
    for e in events:
        if not forward_pass(e):
            continue
        f = frozen.get(e.id.root) or _nearest(plain, e.t.root)
        if f is None or e.pass_ is None or e.pass_.recipient_id is None:
            continue
        verdict = is_offside(
            e.side.value,
            e.pass_.recipient_id.root,
            e.location.root[0].root,
            positions(f),
        )
        if verdict is None:
            continue
        total += 1
        off += verdict
    return off, total


def _t(f: PositionFrame) -> float:
    return f.t.root


def _nearest(sorted_frames: list[PositionFrame], t: float) -> PositionFrame | None:
    if not sorted_frames:
        return None
    return min(sorted_frames, key=lambda f: abs(f.t.root - t))


@dataclass
class Motion:
    """Running max speed (per 0.2 s step) and acceleration (per 0.4 s window) for each player.

    Frames are rounded to 0.1 m, which reads as up to 0.7 m/s of speed and, over one step, 7 m/s^2 of
    acceleration. Acceleration is therefore taken between velocities averaged over three steps each,
    which brings the rounding error under 1 m/s^2.
    """

    history: dict[str, list[tuple[float, float]]] = field(default_factory=dict)
    prev_t: float | None = None
    max_speed: dict[str, float] = field(default_factory=dict)
    max_accel: dict[str, float] = field(default_factory=dict)
    steps: int = 0
    snap_jumps: int = 0  # pinned-actor steps longer than a player can run in one step

    def push(
        self, t: float, players: list[Pos], pinned: frozenset[str] = frozenset()
    ) -> None:
        """Take the next frame. Players in `pinned` had an event since the last frame: the event puts
        them on its location (ADR 0005), so that step is a placement, not running; it is counted, and
        their history restarts from the new spot.
        """
        now = {p.id: (p.x, p.y) for p in players}
        if self.prev_t is not None and t > self.prev_t:
            dt = t - self.prev_t
            moved = [
                math.hypot(xy[0] - h[-1][0], xy[1] - h[-1][1])
                for pid, xy in now.items()
                if (h := self.history.get(pid))
            ]
            if sum(m > RESET_JUMP_M for m in moved) >= RESET_PLAYERS:
                self.history = {}  # a restart moves everyone at once; it is not running
        else:
            dt = FRAME_DT
        if self.prev_t is not None and t <= self.prev_t:
            return
        for pid, xy in now.items():
            h = self.history.setdefault(pid, [])
            if (pid in pinned or RESTART in pinned) and h:
                self.steps += 1
                self.snap_jumps += math.hypot(xy[0] - h[-1][0], xy[1] - h[-1][1]) > (
                    MAX_SPEED_MS * dt
                )
                h.clear()
            elif h:
                self.steps += 1
            h.append(xy)
            del h[: -(2 * ACCEL_STEPS + 1)]
            if len(h) >= 2:
                s = math.hypot(h[-1][0] - h[-2][0], h[-1][1] - h[-2][1]) / dt
                if s > self.max_speed.get(pid, 0.0):
                    self.max_speed[pid] = s
            if len(h) == 2 * ACCEL_STEPS + 1:
                w = ACCEL_STEPS * dt
                va = (
                    (h[ACCEL_STEPS][0] - h[0][0]) / w,
                    (h[ACCEL_STEPS][1] - h[0][1]) / w,
                )
                vb = (
                    (h[-1][0] - h[ACCEL_STEPS][0]) / w,
                    (h[-1][1] - h[ACCEL_STEPS][1]) / w,
                )
                a = math.hypot(vb[0] - va[0], vb[1] - va[1]) / w
                if a > self.max_accel.get(pid, 0.0):
                    self.max_accel[pid] = a
        for pid in [k for k in self.history if k not in now]:
            del self.history[pid]
        self.prev_t = t


def max_speed(frames: Iterable[PositionFrame]) -> dict[str, float]:
    m = Motion()
    for f in frames:
        if f.freeze_frame_of is None:
            m.push(f.t.root, positions(f))
    return m.max_speed


def max_accel(frames: Iterable[PositionFrame]) -> dict[str, float]:
    m = Motion()
    for f in frames:
        if f.freeze_frame_of is None:
            m.push(f.t.root, positions(f))
    return m.max_accel


def overlapping(players: list[Pos]) -> bool:
    for i, a in enumerate(players):
        for b in players[i + 1 :]:
            if a.side == b.side and math.hypot(a.x - b.x, a.y - b.y) < OVERLAP_M:
                return True
    return False


def teammate_overlap(frames: Iterable[PositionFrame]) -> float:
    """Share of frames with two teammates closer than 1.5 m."""
    n = hit = 0
    for f in frames:
        if f.freeze_frame_of is not None:
            continue
        n += 1
        hit += overlapping(positions(f))
    return hit / n if n else 0.0


def back_line_spread(side: str, players: list[Pos]) -> float | None:
    """Spread in x (max - min) of the four deepest outfielders of a side."""
    mine = [p for p in players if p.side == side and not p.id.endswith("-01")]
    if len(mine) < BACK_LINE:
        return None
    sign = attack_sign(side)
    deepest = sorted(mine, key=lambda p: sign * p.x)[:BACK_LINE]
    xs = [p.x for p in deepest]
    return max(xs) - min(xs)


def line_coherence(frames: Iterable[PositionFrame]) -> float:
    """Mean spread in x of each back line over the frames in which its side is out of possession."""
    total = n = 0.0
    for f in frames:
        if f.freeze_frame_of is not None or f.possession is None:
            continue
        players = positions(f)
        for side in ("home", "away"):
            if f.possession.value == side:
                continue
            s = back_line_spread(side, players)
            if s is not None:
                total += s
                n += 1
    return total / n if n else 0.0


@dataclass
class Report:
    """One match's realism numbers, built in a single pass over what run() yields."""

    offside: int = 0
    forward_passes: int = 0
    motion: Motion = field(default_factory=Motion)
    pinned: set[str] = field(default_factory=set)
    frames: int = 0
    overlap_frames: int = 0
    coherence_sum: float = 0.0
    coherence_n: int = 0

    def feed(self, kind: str, event: Event | None, frame: PositionFrame | None) -> None:
        if kind == "freeze" and self._pending is not None and frame is not None:
            e, self._pending = self._pending, None
            if e.pass_ is not None and e.pass_.recipient_id is not None:
                verdict = is_offside(
                    e.side.value,
                    e.pass_.recipient_id.root,
                    e.location.root[0].root,
                    positions(frame),
                )
                if verdict is not None:
                    self.forward_passes += 1
                    self.offside += verdict
        elif kind == "event" and event is not None:
            if event.type.value == "period_start":
                self.pinned.add(
                    RESTART
                )  # everyone is set up again, which is not running
            if event.player_id is not None:
                self.pinned.add(event.player_id.root)
            if forward_pass(event):
                self._pending = event
        elif kind == "frame" and frame is not None:
            players = positions(frame)
            self.motion.push(frame.t.root, players, frozenset(self.pinned))
            self.pinned.clear()
            self.frames += 1
            self.overlap_frames += overlapping(players)
            if frame.possession is not None:
                for side in ("home", "away"):
                    if frame.possession.value != side:
                        s = back_line_spread(side, players)
                        if s is not None:
                            self.coherence_sum += s
                            self.coherence_n += 1

    _pending: Event | None = None

    def summary(self) -> dict[str, float]:
        speeds = self.motion.max_speed.values()
        accels = self.motion.max_accel.values()
        return {
            "forward_passes": self.forward_passes,
            "offside_passes": self.offside,
            "offside_share": self.offside / self.forward_passes
            if self.forward_passes
            else 0.0,
            "snap_jumps": self.motion.snap_jumps,
            "steps": self.motion.steps,
            "max_speed": max(speeds, default=0.0),
            "max_accel": max(accels, default=0.0),
            "teammate_overlap": self.overlap_frames / self.frames
            if self.frames
            else 0.0,
            "line_coherence": self.coherence_sum / self.coherence_n
            if self.coherence_n
            else 0.0,
        }
