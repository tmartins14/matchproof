"""The beat detector: key moments found in the match as it streams, and the same moments in batch.

BeatDetector.push() takes the same time-ordered items as FactEngine (events, frames, freeze frames).
detect_all() merges a finished match into that order and feeds it through one detector, so the two
paths are the same code and give the same beats and ids. Nothing here reads a clock or draws a random
number.

Two things happen later than the moment they describe:
- A beat anchored on a shot or card waits for that event's freeze frame, so its facts include the
  freeze-frame facts. The freeze frame follows its event at the same match time.
- A goal or red card schedules a follow-up check FOLLOW_UP_S later; momentum_swing is emitted if the
  match changed enough since. Checks still waiting at full time run then.
"""

import math
import re
from collections import defaultdict, deque
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from contracts.models import Beat, Event, Fact, PositionFrame

from .display import minute_of
from .extract_events import CARD_METRICS, SEQUENCE_METRICS, SHOT_METRICS
from .extract_positions import is_sample_time
from .football import (
    HIGH_TURNOVER_DISTANCE_M,
    SIDES,
    TOUCH_TYPES,
    distance_to_goal,
    in_opponent_half,
    is_ball_won,
    location,
)
from .registry import FactRegistry
from .since import last_minutes, since

# ---- kinds ------------------------------------------------------------------------------------
COUNTER_GOAL = "counter_goal"
SET_PIECE_GOAL = "set_piece_goal"
OPEN_PLAY_GOAL = "open_play_goal"
HIGH_TURNOVER_CHANCE = "high_turnover_chance"
BIG_CHANCE = "big_chance"
CARD = "card"
TERRITORIAL_SPELL = "territorial_spell"
MOMENTUM_SWING = "momentum_swing"
HIGH_TURNOVER_GOAL = "high_turnover_goal"
GOAL_KINDS = frozenset(
    {COUNTER_GOAL, SET_PIECE_GOAL, HIGH_TURNOVER_GOAL, OPEN_PLAY_GOAL}
)
# Most specific first; when several kinds match one shot, the first of these is the beat.
SPECIFICITY = (
    COUNTER_GOAL,
    SET_PIECE_GOAL,
    HIGH_TURNOVER_GOAL,
    OPEN_PLAY_GOAL,
    HIGH_TURNOVER_CHANCE,
    BIG_CHANCE,
)

# ---- thresholds -------------------------------------------------------------------------------
COUNTER_MAX_S = 15.0  # a goal is a counter when the ball was won in the scorer's half this long before the shot
SET_PIECE_STARTS = frozenset(
    {"corner", "free_kick"}
)  # a passage that starts here is a set piece
SET_PIECE_MAX_S = (
    10.0  # ...and is a set-piece goal only if the shot follows the restart this soon
)
RESTART_TYPES = SET_PIECE_STARTS | {
    "throw_in",
    "goal_kick",
    "kick_off",
}  # where play restarts
HIGH_TURNOVER_MAX_M = HIGH_TURNOVER_DISTANCE_M  # ball won this close to the opponent's goal is a high turnover
HIGH_TURNOVER_SHOT_S = (
    12.0  # a high turnover is a beat when a shot follows within this long
)
BIG_CHANCE_XG = 0.30  # a shot this good that does not score is a big chance
DEBOUNCE_S = (
    60.0  # no two beats of one kind for one side closer than this; goals are exempt
)
SPELL_WINDOW_S = 600.0  # territory share is measured over this rolling stretch
SPELL_OPEN_SHARE = 0.65  # a spell opens when a side's territory share reaches this
SPELL_CLOSE_SHARE = 0.55  # and closes when it falls below this
SPELL_MAX_S = 900.0  # a spell that has not closed gets its beat after this long
SPELL_WARMUP_S = (
    SPELL_WINDOW_S  # no spell is judged until a full window of play has gone
)
SPELL_MIN_TOUCHES = 40  # fewest touches in the window before a share means anything
FOLLOW_UP_S = 900.0  # how long after a goal or red card the momentum check runs
MIN_SINCE_S = 480.0  # a follow-up needs at least this much play since its anchor, or it is skipped
SWING_BACK_LINE_M = 4.0  # back line moved at least this far
SWING_COMPACTNESS = (
    0.10  # compactness changed by at least this fraction of its earlier value
)
SWING_POSSESSION_PTS = 10.0  # possession share moved at least this many points
SWING_TERRITORY_PTS = 10.0  # territory moved at least this many points
STOPPAGE_AFTER_MIN = {
    1: 45,
    2: 90,
}  # minutes after which a half's labels read 45+n and 90+n
SECONDS_PER_MINUTE = 60.0

# ---- salience (0 to 1): goals, then red cards, then follow-ups, then chances, then spells -------
SALIENCE_GOAL = 0.90  # every goal
SALIENCE_RED_CARD = 0.80  # every red card
SALIENCE_SWING_BASE = 0.50  # follow-up that only just crosses a threshold
SALIENCE_SWING_RANGE = (
    0.25  # added as the largest change reaches three times its threshold
)
SALIENCE_CHANCE_BASE = 0.30  # chance with no xG
SALIENCE_CHANCE_RANGE = 0.20  # added as xG reaches CHANCE_XG_CAP
CHANCE_XG_CAP = 0.50  # xG at which a chance is worth the full range
SALIENCE_SPELL_BASE = 0.10  # spell that only just reaches the open share
SALIENCE_SPELL_RANGE = 0.20  # added as the peak share reaches SPELL_PEAK_CAP
SPELL_PEAK_CAP = 0.85  # peak share at which a spell is worth the full range
SWING_RATIO_CAP = (
    3.0  # change as a multiple of its threshold at which salience stops growing
)

FREEZE_BEAT_METRICS = (
    "attackers_v_defenders",
    "attackers_ahead_of_ball",
    "zone_attackers",
    "zone_defenders",
    "defenders_between_ball_and_goal",
    "defenders_drawn",
    "shooter_nearest_defender",
)  # freeze-frame facts that describe a shot or card; others are for MCP lookups
SWING_METRICS = ("back_line_height", "compactness", "possession_share", "territory")
SWING_CHANGE_METRICS = ("back_line_change", "compactness_change")
FACT_NAME = re.compile(r"^(?P<metric>[a-z_]+)\((?P<side>home|away), (?P<rest>.*)\)$")


@dataclass
class _Candidate:
    """A beat waiting for its anchor's freeze frame."""

    kind: str
    side: str
    anchor: Event
    salience: float
    fact_names: list[str]


@dataclass
class _Spell:
    t_open: float = 0.0
    anchor_id: str = ""
    peak: float = 0.0
    emitted: bool = False
    open: bool = False


@dataclass
class _Swing:
    """What a follow-up check found: whether it is a beat, how big, and its facts."""

    ratio: float = 0.0
    facts: list[Fact] = field(default_factory=list)


def minute_text(t: float, period: int) -> str:
    """41, or 45+2 / 90+3 once the half is past its 45th / 90th minute."""
    m = minute_of(t)
    limit = STOPPAGE_AFTER_MIN[period]
    return f"{limit}+{m - limit}" if m > limit else str(m)


def beat_id(anchor_event_id: str, kind: str) -> str:
    return f"bt-{anchor_event_id.removeprefix('ev-')}-{kind}"


def chance_salience(xg: float) -> float:
    return SALIENCE_CHANCE_BASE + SALIENCE_CHANCE_RANGE * min(xg / CHANCE_XG_CAP, 1.0)


def swing_salience(ratio: float) -> float:
    """ratio is the largest change as a multiple of its threshold, 1 or more."""
    grown = min((ratio - 1.0) / (SWING_RATIO_CAP - 1.0), 1.0)
    return SALIENCE_SWING_BASE + SALIENCE_SWING_RANGE * max(grown, 0.0)


def spell_salience(peak: float) -> float:
    grown = (peak - SPELL_OPEN_SHARE) / (SPELL_PEAK_CAP - SPELL_OPEN_SHARE)
    return SALIENCE_SPELL_BASE + SALIENCE_SPELL_RANGE * min(max(grown, 0.0), 1.0)


class BeatDetector:
    """Takes the match in time order and returns each beat as soon as it can be known."""

    def __init__(self) -> None:
        self._events: list[Event] = []
        self._samples: list[PositionFrame] = []
        self._groups: dict[int, list[Event]] = {}
        self._awaiting: dict[str, list[_Candidate]] = defaultdict(list)
        self._follow_ups: deque[Event] = deque()
        self._last_beat: dict[tuple[str, str], float] = {}
        self._touches: deque[tuple[float, bool, bool]] = deque()
        self._in_half = {"home": 0, "away": 0}
        self._spells = {side: _Spell() for side in SIDES}
        self._p2_start: float | None = None
        self._finished = False

    def push(self, item: Event | PositionFrame, registry: FactRegistry) -> list[Beat]:
        """Take the next event or frame (freeze frames included); return the beats it completes."""
        if isinstance(item, Event):
            self._events.append(item)
            if item.type.value == "period_start" and item.period.value == 2:
                self._p2_start = item.t.root
            out = self._due_follow_ups(item.t.root, registry)
            out += self._on_event(item, registry)
            if item.type.value == "period_end" and item.period.value == 2:
                out += self.finish(registry)
            return out
        if item.freeze_frame_of is not None:
            return self._emit_awaiting(item.freeze_frame_of.root, registry)
        if is_sample_time(item.t.root):
            self._samples.append(item)
        return self._due_follow_ups(item.t.root, registry)

    def finish(self, registry: FactRegistry) -> list[Beat]:
        """Settle whatever is still waiting, for full time or a stream that stopped early."""
        if self._finished:
            return []
        self._finished = True
        out: list[Beat] = []
        for anchor_id in list(self._awaiting):
            out += self._emit_awaiting(anchor_id, registry)
        out += self._due_follow_ups(math.inf, registry)
        now = self._events[-1].t.root if self._events else 0.0
        for side in SIDES:
            spell = self._spells[side]
            if spell.open and not spell.emitted:
                out += self._close_spell(side, now, registry)
        return out

    # ---- events --------------------------------------------------------------------------------
    def _on_event(self, e: Event, registry: FactRegistry) -> list[Beat]:
        kind = e.type.value
        out: list[Beat] = []
        if kind in TOUCH_TYPES:
            out += self._update_spells(e, registry)
        pid = e.possession_id
        if kind == "shot":
            self._shot_candidates(e)
        elif pid is not None and kind in TOUCH_TYPES:
            self._groups.setdefault(pid, []).append(e)
        if kind == "card" and e.outcome is not None and e.outcome.value == "red":
            self._card_candidate(e)
        return out

    def _shot_candidates(self, shot: Event) -> None:
        side = shot.side.value
        sid = shot.id.root
        pid = shot.possession_id
        group = self._groups.pop(pid, []) if pid is not None else []
        mine = [x for x in group if x.side == shot.side]
        # A possession id can span several regains and restarts, so the passage that ends in the shot
        # begins at the latest restart or regain before it.
        begin = next(
            (
                x
                for x in reversed(mine)
                if x.type.value in RESTART_TYPES or is_ball_won(x)
            ),
            None,
        )
        goal = shot.outcome is not None and shot.outcome.value == "goal"
        xg = shot.shot.xg if shot.shot is not None else 0.0
        names = [
            *(f"shot({sid}).{m.removeprefix('shot.')}" for m in SHOT_METRICS),
            *(
                f"sequence({sid}).{m.removeprefix('sequence.')}"
                for m in SEQUENCE_METRICS
            ),
            *(f"freeze_frame({sid}).{m}" for m in FREEZE_BEAT_METRICS),
        ]
        win = begin if begin is not None and is_ball_won(begin) else None
        high_turnover = (
            win is not None
            and distance_to_goal(side, location(win)) <= HIGH_TURNOVER_MAX_M
            and shot.t.root - win.t.root <= HIGH_TURNOVER_SHOT_S
        )
        matched: list[str] = []
        if goal:
            if (
                begin is not None
                and begin.type.value in SET_PIECE_STARTS
                and shot.t.root - begin.t.root <= SET_PIECE_MAX_S
            ):
                matched.append(SET_PIECE_GOAL)
            if (
                win is not None
                and not in_opponent_half(side, location(win)[0])
                and shot.t.root - win.t.root <= COUNTER_MAX_S
            ):
                matched.append(COUNTER_GOAL)
            if high_turnover:
                matched.append(HIGH_TURNOVER_GOAL)
            matched.append(OPEN_PLAY_GOAL)
            self._follow_ups.append(shot)
        else:
            if high_turnover:
                matched.append(HIGH_TURNOVER_CHANCE)
            if xg >= BIG_CHANCE_XG:
                matched.append(BIG_CHANCE)
        # One beat per anchor: the most specific kind that matched, unless debounce silences it. Every
        # candidate cites the same shot, sequence and freeze-frame facts, so the losers' facts are
        # already the winner's.
        for kind in sorted(matched, key=SPECIFICITY.index):
            if kind in GOAL_KINDS:
                salience = SALIENCE_GOAL
            elif self._debounce_ok(kind, side, shot.t.root):
                salience = chance_salience(xg)
            else:
                continue
            self._record(kind, side, shot.t.root)
            self._awaiting[sid].append(_Candidate(kind, side, shot, salience, names))
            return

    def _card_candidate(self, card: Event) -> None:
        sid = card.id.root
        names = [
            *(f"card({sid}).{m.removeprefix('card.')}" for m in CARD_METRICS),
            *(f"freeze_frame({sid}).{m}" for m in FREEZE_BEAT_METRICS),
        ]
        side = card.side.value
        if self._debounce(CARD, side, card.t.root):
            self._awaiting[sid].append(
                _Candidate(CARD, side, card, SALIENCE_RED_CARD, names)
            )
        self._follow_ups.append(card)

    def _debounce_ok(self, kind: str, side: str, t: float) -> bool:
        """True when no beat of this kind for this side is closer than DEBOUNCE_S."""
        last = self._last_beat.get((kind, side))
        return last is None or t - last >= DEBOUNCE_S

    def _record(self, kind: str, side: str, t: float) -> None:
        self._last_beat[(kind, side)] = t

    def _debounce(self, kind: str, side: str, t: float) -> bool:
        """True (and the beat is recorded) when no beat of this kind for this side is too close."""
        if not self._debounce_ok(kind, side, t):
            return False
        self._record(kind, side, t)
        return True

    def _emit_awaiting(self, event_id: str, registry: FactRegistry) -> list[Beat]:
        out: list[Beat] = []
        for c in self._awaiting.pop(event_id, []):
            ids = [
                registry.by_name(n).id.root
                for n in c.fact_names
                if registry.has_name(n)
            ]
            t = c.anchor.t.root
            period = c.anchor.period.value
            out.append(
                self._beat(
                    c.kind,
                    c.side,
                    c.anchor,
                    ids,
                    c.salience,
                    t,
                    t,
                    t,
                    f"{minute_text(t, period)}′",
                )
            )
        return out

    def _beat(
        self,
        kind: str,
        side: str,
        anchor: Event,
        fact_ids: list[str],
        salience: float,
        t_detect: float,
        t_from: float,
        t_to: float,
        label: str,
        planted: bool = True,
    ) -> Beat:
        """`planted` is False for beats the detector finds afterwards (follow-ups and spells)."""
        if not fact_ids:
            raise ValueError(f"beat {kind} on {anchor.id.root} has no facts")
        raw: dict[str, object] = {
            "id": beat_id(anchor.id.root, kind),
            "kind": kind,
            "origin": "planted" if planted and anchor.planted_beat_id else "detected",
            "side": side,
            "t_detect": t_detect,
            "t_from": t_from,
            "t_to": t_to,
            "label": label,
            "anchor_event_id": anchor.id.root,
            "fact_ids": list(dict.fromkeys(fact_ids)),
            "salience": round(min(max(salience, 0.0), 1.0), 4),
        }
        if planted and anchor.planted_beat_id:
            raw["planted_beat_id"] = anchor.planted_beat_id
        return Beat.model_validate(raw)

    def _span_label(self, t_from: float, t_to: float) -> str:
        a = minute_text(t_from, self._period_of(t_from))
        b = minute_text(t_to, self._period_of(t_to))
        return f"{a}–{b}′"

    def _period_of(self, t: float) -> int:
        return 2 if self._p2_start is not None and t >= self._p2_start else 1

    # ---- territorial spells --------------------------------------------------------------------
    def _update_spells(self, e: Event, registry: FactRegistry) -> list[Beat]:
        t = e.t.root
        x = location(e)[0]
        home, away = in_opponent_half("home", x), in_opponent_half("away", x)
        self._touches.append((t, home, away))
        self._in_half["home"] += home
        self._in_half["away"] += away
        while self._touches[0][0] < t - SPELL_WINDOW_S:
            _, h, a = self._touches.popleft()
            self._in_half["home"] -= h
            self._in_half["away"] -= a
        total = len(self._touches)
        if t < SPELL_WARMUP_S or total < SPELL_MIN_TOUCHES:
            return []
        out: list[Beat] = []
        for side in SIDES:
            share = self._in_half[side] / total
            spell = self._spells[side]
            if not spell.open:
                if share >= SPELL_OPEN_SHARE:
                    self._spells[side] = _Spell(t, e.id.root, share, False, True)
                continue
            spell.peak = max(spell.peak, share)
            if share < SPELL_CLOSE_SHARE:
                if not spell.emitted:
                    out += self._close_spell(side, t, registry)
                self._spells[side] = _Spell()
            elif not spell.emitted and t - spell.t_open >= SPELL_MAX_S:
                out += self._close_spell(side, t, registry)
        return out

    def _close_spell(self, side: str, t: float, registry: FactRegistry) -> list[Beat]:
        spell = self._spells[side]
        spell.emitted = True
        if not self._debounce(TERRITORIAL_SPELL, side, t):
            return []
        minutes = max(1, math.ceil((t - spell.t_open) / SECONDS_PER_MINUTE))
        facts = last_minutes(minutes, registry, self._events)
        anchor = next(x for x in self._events if x.id.root == spell.anchor_id)
        return [
            self._beat(
                TERRITORIAL_SPELL,
                side,
                anchor,
                [f.id.root for f in facts],
                spell_salience(spell.peak),
                t,
                spell.t_open,
                t,
                self._span_label(spell.t_open, t),
                planted=False,
            )
        ]

    # ---- follow-ups ----------------------------------------------------------------------------
    def _due_follow_ups(self, t: float, registry: FactRegistry) -> list[Beat]:
        out: list[Beat] = []
        while self._follow_ups and self._follow_ups[0].t.root + FOLLOW_UP_S <= t:
            anchor = self._follow_ups.popleft()
            beat = self._follow_up(anchor, registry)
            if beat is not None:
                out.append(beat)
        return out

    def _follow_up(self, anchor: Event, registry: FactRegistry) -> Beat | None:
        now = max([self._events[-1].t.root] + [s.t.root for s in self._samples[-1:]])
        if now - anchor.t.root < MIN_SINCE_S:
            return None  # e.g. a goal in stoppage time: too little play to say what changed
        made = since(anchor.id.root, registry, self._events, self._samples)
        swing = _swing(made)
        if swing.ratio < 1.0:
            return None
        side = anchor.side.value
        if not self._debounce(MOMENTUM_SWING, side, now):
            return None
        t0 = anchor.t.root
        return self._beat(
            MOMENTUM_SWING,
            side,
            anchor,
            [f.id.root for f in swing.facts],
            swing_salience(swing.ratio),
            now,
            t0,
            now,
            self._span_label(t0, now),
            planted=False,
        )


def _swing(made: Sequence[Fact]) -> _Swing:
    """The largest change as a multiple of its threshold, and the facts that show it."""
    values: dict[tuple[str, str, str], float] = {}
    keep: list[Fact] = []
    for f in made:
        m = FACT_NAME.match(f.name)
        if m is None or not isinstance(f.value, int | float):
            continue
        metric, side, rest = m["metric"], m["side"], m["rest"]
        if metric not in SWING_METRICS and metric not in SWING_CHANGE_METRICS:
            continue
        phase = (
            "before"
            if rest.startswith("before ")
            else "since"
            if rest.startswith("since ")
            else "change"
        )
        values[(metric, side, phase)] = float(f.value)
        keep.append(f)
    ratio = 0.0
    for side in SIDES:
        ratio = max(
            ratio,
            values.get(("back_line_change", side, "change"), 0.0) / SWING_BACK_LINE_M,
        )
        for metric, scale in (
            ("compactness", None),
            ("possession_share", SWING_POSSESSION_PTS),
            ("territory", SWING_TERRITORY_PTS),
        ):
            b = values.get((metric, side, "before"))
            a = values.get((metric, side, "since"))
            if a is None or b is None:
                continue
            if scale is None:
                if b > 0:
                    ratio = max(ratio, abs(a - b) / b / SWING_COMPACTNESS)
            else:
                ratio = max(ratio, abs(a - b) * 100.0 / scale)
    return _Swing(ratio, keep)


def merge_stream(
    events: Iterable[Event],
    frames: Iterable[PositionFrame],
    freeze_frames: Iterable[PositionFrame],
) -> list[Event | PositionFrame]:
    """The order sim.positions.run yields: an event, its freeze frame, then frames at that time."""
    evs = list(events)
    owner = {e.id.root: e for e in evs}
    keyed: list[tuple[tuple[float, float, int], Event | PositionFrame]] = []
    keyed += [((e.t.root, e.seq, 0), e) for e in evs]
    for ff in freeze_frames:
        if ff.freeze_frame_of is not None:
            o = owner[ff.freeze_frame_of.root]
            keyed.append(((o.t.root, o.seq, 1), ff))
    keyed += [((f.t.root, math.inf, 2), f) for f in frames]
    keyed.sort(key=lambda kv: kv[0])
    return [item for _, item in keyed]


def detect_all(
    events: Iterable[Event],
    frames: Iterable[PositionFrame],
    freeze_frames: Iterable[PositionFrame],
    registry: FactRegistry,
) -> list[Beat]:
    """Every beat of a finished match; equals the beats BeatDetector gives while it streams.

    `registry` is the match's fact registry (extract_all); on-demand facts for beats are added to it.
    """
    detector = BeatDetector()
    out: list[Beat] = []
    for item in merge_stream(events, frames, freeze_frames):
        out += detector.push(item, registry)
    out += detector.finish(registry)
    return out
