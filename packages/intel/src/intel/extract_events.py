"""Event extractors: per-team counts and shares over a span, and per-event sequence, shot and card facts."""

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from contracts.models import Event, Fact

from .display import minute_of, render_minute
from .football import (
    HIGH_TURNOVER_DISTANCE_M,
    SIDES,
    TOUCH_TYPES,
    distance_to_goal,
    in_attacking_third,
    in_opponent_half,
    is_ball_won,
    is_complete_pass,
    location,
    opponent,
)
from .registry import build_fact

EXTRACTOR = "extract_events"
SEQUENCE_EXTRACTOR = "extract_sequences"
DISCIPLINE_EXTRACTOR = "extract_discipline"
ON_TARGET = frozenset({"goal", "saved"})  # shot outcomes that count as on target
SQUAD_SIZE = 11  # players a side starts with
LANGS = ("en", "es")

METRICS = (
    "passes",
    "pass_completion",
    "shots",
    "goals",
    "xg",
    "possession_share",
    "corners",
    "fouls",
    "cards",
    "territory",
    "field_tilt",
    "high_turnovers",
    "pressures_in_opp_third",
    "touches_in_opponent_half",
    "press_rate",
)
SEQUENCE_METRICS = (
    "sequence.seconds",
    "sequence.passes",
    "sequence.ball_won_distance",
    "sequence.start_clock",
    "sequence.shot_clock",
)
SHOT_METRICS = (
    "shot.xg",
    "shot.outcome",
    "shot.on_target",
    "shot.minute",
    "shot.shooter",
)
CARD_METRICS = ("card.kind", "card.players_after", "card.minute")


@dataclass(frozen=True)
class Span:
    """A stretch of the match that span facts describe: a window, a half or the whole match."""

    label: str  # win-04, p1 or match
    period: int | None
    t_from: float
    t_to: float
    source_ids: tuple[str, ...]


def buildup_counts(events: Sequence[Event], pressing: str) -> tuple[int, int]:
    """(pressed, total) of the other side's build-ups: possessions that begin in their own half."""
    builder = opponent(pressing)
    first: dict[int, Event] = {}
    pressed: set[int] = set()
    for e in events:
        pid = e.possession_id
        if pid is None:
            continue
        if e.side.value == builder and pid not in first and e.type.value in TOUCH_TYPES:
            first[pid] = e
        elif e.side.value == pressing and e.type.value == "pressure":
            pressed.add(pid)
    starts = [
        pid for pid, e in first.items() if not in_opponent_half(builder, location(e)[0])
    ]
    return sum(1 for pid in starts if pid in pressed), len(starts)


def side_values(
    events: Sequence[Event], side: str
) -> list[tuple[str, float | int, str]]:
    """(metric, value, unit) for one side over the events. Shares with no denominator are left out."""
    c: Counter[str] = Counter()
    xg = 0.0
    other = opponent(side)
    for e in events:
        t = e.type.value
        mine = e.side.value == side
        loc = location(e)
        if t == "pass":
            if mine:
                c["passes"] += 1
            if is_complete_pass(e):
                c["complete" if mine else "opp_complete"] += 1
        elif t == "shot" and mine:
            c["shots"] += 1
            if e.shot is not None:
                xg += e.shot.xg
            if e.outcome is not None and e.outcome.value == "goal":
                c["goals"] += 1
        elif t == "corner" and mine:
            c["corners"] += 1
        elif t == "foul" and mine:
            c["fouls"] += 1
        elif t == "card" and mine:
            c["cards"] += 1
        elif t == "pressure" and mine and in_attacking_third(side, loc[0]):
            c["pressures_in_opp_third"] += 1
        if (
            mine
            and is_ball_won(e)
            and distance_to_goal(side, loc) <= HIGH_TURNOVER_DISTANCE_M
        ):
            c["high_turnovers"] += 1
        if t in TOUCH_TYPES:
            c["touches"] += 1
            if in_opponent_half(side, loc[0]):
                c["in_opponent_half"] += 1
                if mine:
                    c["touches_in_opponent_half"] += 1
            if mine and in_attacking_third(side, loc[0]):
                c["final_third_mine"] += 1
            elif not mine and in_attacking_third(other, loc[0]):
                c["final_third_theirs"] += 1
    out: list[tuple[str, float | int, str]] = [("passes", c["passes"], "count")]
    if c["passes"]:
        out.append(("pass_completion", c["complete"] / c["passes"], "pct"))
    out += [
        ("shots", c["shots"], "count"),
        ("goals", c["goals"], "count"),
        ("xg", xg, "xg"),
    ]
    both_complete = c["complete"] + c["opp_complete"]
    if both_complete:
        out.append(("possession_share", c["complete"] / both_complete, "pct"))
    out += [
        ("corners", c["corners"], "count"),
        ("fouls", c["fouls"], "count"),
        ("cards", c["cards"], "count"),
    ]
    if c["touches"]:
        out.append(("territory", c["in_opponent_half"] / c["touches"], "pct"))
    both_final = c["final_third_mine"] + c["final_third_theirs"]
    if both_final:
        out.append(("field_tilt", c["final_third_mine"] / both_final, "pct"))
    out += [
        ("high_turnovers", c["high_turnovers"], "count"),
        ("pressures_in_opp_third", c["pressures_in_opp_third"], "count"),
        ("touches_in_opponent_half", c["touches_in_opponent_half"], "count"),
    ]
    pressed, builds = buildup_counts(events, side)
    if builds:
        out.append(("press_rate", pressed / builds, "pct"))
    return out


def span_facts(events: Sequence[Event], span: Span) -> list[Fact]:
    """Per-team facts over one span, named metric(side, label)."""
    facts: list[Fact] = []
    for side in SIDES:
        scope: dict[str, object] = {
            "side": side,
            "t_from": span.t_from,
            "t_to": span.t_to,
        }
        if span.period is not None:
            scope["period"] = span.period
        for metric, value, unit in side_values(events, side):
            facts.append(
                build_fact(
                    f"{metric}({side}, {span.label})",
                    value,
                    unit,
                    span.source_ids,
                    EXTRACTOR,
                    scope,
                )
            )
    return facts


class EventObserver:
    """Per-event facts that need what came before: sequences into shots, shots, and cards.

    The batch and incremental paths both feed events through one of these in stream order.
    """

    def __init__(self, roster: Mapping[str, str] | None = None) -> None:
        self._roster = roster or {}
        self._groups: dict[int, list[Event]] = {}
        self._yellows: set[str] = set()
        self._dismissed = {"home": 0, "away": 0}

    def observe(self, e: Event) -> list[Fact]:
        kind = e.type.value
        facts: list[Fact] = []
        if e.possession_id is not None and kind in TOUCH_TYPES:
            group = self._groups.setdefault(e.possession_id, [])
            if kind == "shot":
                facts += self._shot_facts(e)
                facts += self._sequence_facts(e, group)
                group.clear()  # a later shot in the same possession starts a new sequence
            else:
                group.append(e)
        elif kind == "shot":
            facts += self._shot_facts(e)
        if kind == "card":
            facts += self._card_facts(e)
        return facts

    def _sequence_facts(self, shot: Event, group: list[Event]) -> list[Fact]:
        mine = [x for x in group if x.side == shot.side] + [shot]
        sid = shot.id.root
        sources = [x.id.root for x in mine]
        side = shot.side.value
        start = mine[0]
        scope: dict[str, object] = {
            "side": side,
            "t_from": start.t.root,
            "t_to": shot.t.root,
        }

        def fact(
            suffix: str,
            value: float,
            unit: str,
            display: dict[str, list[str]] | None = None,
        ) -> Fact:
            return build_fact(
                f"sequence({sid}).{suffix}",
                value,
                unit,
                sources,
                SEQUENCE_EXTRACTOR,
                scope,
                display,
            )

        facts = [
            fact("seconds", shot.t.root - start.t.root, "s"),
            fact("passes", sum(1 for x in mine if x.type.value == "pass"), "count"),
            fact(
                "start_clock",
                start.t.root,
                "s",
                {
                    lang: render_minute(start.t.root, lang, start.period.value)
                    for lang in LANGS
                },
            ),
            fact(
                "shot_clock",
                shot.t.root,
                "s",
                {
                    lang: render_minute(shot.t.root, lang, shot.period.value)
                    for lang in LANGS
                },
            ),
        ]
        if is_ball_won(start):
            facts.append(
                fact("ball_won_distance", distance_to_goal(side, location(start)), "m")
            )
        return facts

    def _shot_facts(self, shot: Event) -> list[Fact]:
        sid = shot.id.root
        scope: dict[str, object] = {
            "side": shot.side.value,
            "t_from": shot.t.root,
            "t_to": shot.t.root,
        }
        outcome = shot.outcome.value if shot.outcome is not None else "none"
        facts = [
            build_fact(f"shot({sid}).outcome", outcome, "", [sid], EXTRACTOR, scope),
            build_fact(
                f"shot({sid}).on_target",
                outcome in ON_TARGET,
                "",
                [sid],
                EXTRACTOR,
                scope,
            ),
            build_fact(
                f"shot({sid}).minute",
                minute_of(shot.t.root),
                "",
                [sid],
                EXTRACTOR,
                scope,
                {
                    lang: render_minute(shot.t.root, lang, shot.period.value)
                    for lang in LANGS
                },
            ),
        ]
        if shot.player_id is not None:
            who = shot.player_id.root
            facts.append(
                build_fact(
                    f"shot({sid}).shooter",
                    self._roster.get(who, who),
                    "",
                    [sid],
                    EXTRACTOR,
                    scope,
                )
            )
        if shot.shot is not None:
            facts.append(
                build_fact(
                    f"shot({sid}).xg", shot.shot.xg, "xg", [sid], EXTRACTOR, scope
                )
            )
        return facts

    def _card_facts(self, card: Event) -> list[Fact]:
        sid = card.id.root
        side = card.side.value
        colour = card.outcome.value if card.outcome is not None else "none"
        player = card.player_id.root if card.player_id is not None else sid
        # A second booking, or a red after a yellow, is a second yellow.
        kind = "second_yellow" if player in self._yellows else colour
        if colour == "yellow":
            self._yellows.add(player)
        if kind in ("second_yellow", "red"):
            self._dismissed[side] += 1
        scope: dict[str, object] = {
            "side": side,
            "t_from": card.t.root,
            "t_to": card.t.root,
        }
        return [
            build_fact(
                f"card({sid}).kind", kind, "", [sid], DISCIPLINE_EXTRACTOR, scope
            ),
            build_fact(
                f"card({sid}).players_after",
                SQUAD_SIZE - self._dismissed[side],
                "count",
                [sid],
                DISCIPLINE_EXTRACTOR,
                scope,
            ),
            build_fact(
                f"card({sid}).minute",
                minute_of(card.t.root),
                "",
                [sid],
                DISCIPLINE_EXTRACTOR,
                scope,
                {
                    lang: render_minute(card.t.root, lang, card.period.value)
                    for lang in LANGS
                },
            ),
        ]
