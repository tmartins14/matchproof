"""Storylines, tactics and the tactics-to-brief template (ADR 0004)."""

import hashlib
import itertools
import random
from collections.abc import Sequence
from dataclasses import dataclass

from contracts.models import MatchBrief

from .roster import make_roster
from .tactics import FORMATIONS


@dataclass(frozen=True)
class TeamTactics:
    name: str
    short: str
    formation: str = "4-3-3"
    press: float = 0.5
    directness: float = 0.5
    line_height: float = 0.5


DEFAULT_HOME = TeamTactics("Rivermouth", "RIV")
DEFAULT_AWAY = TeamTactics("Ashford Vale", "ASH")

# (kind, side, minute_from, minute_to)
PlantedSpec = tuple[str, str, int, int]


@dataclass(frozen=True)
class Storyline:
    text: str
    beats: list[PlantedSpec]
    final_score: tuple[int, int]  # home, away


STORYLINES: dict[str, Storyline] = {
    "late_comeback": Storyline(
        "Ashford score first on the break; Rivermouth equalise from a set piece and win it late.",
        [
            ("counter_goal", "away", 35, 45),
            ("set_piece_goal", "home", 75, 85),
            ("high_turnover_goal", "home", 90, 95),
        ],
        (2, 1),
    ),
    "red_card_flip": Storyline(
        "A goalless first half, then a red card on the hour flips the game.",
        [
            ("red_card", "away", 58, 62),
            ("open_play_goal", "home", 65, 75),
            ("open_play_goal", "home", 80, 88),
        ],
        (2, 0),
    ),
    "smash_and_grab": Storyline(
        "Rivermouth dominate the ball but lose 1–0 to a single counter.",
        [("counter_goal", "away", 60, 75)],
        (0, 1),
    ),
    "end_to_end": Storyline(
        "End to end, 3–3, with an equaliser in stoppage time.",
        [
            ("open_play_goal", "home", 10, 20),
            ("counter_goal", "away", 25, 35),
            ("set_piece_goal", "home", 40, 45),
            ("open_play_goal", "away", 55, 65),
            ("high_turnover_goal", "home", 70, 80),
            ("penalty", "away", 91, 95),
        ],
        (3, 3),
    ),
}

GOAL_KINDS = {
    "counter_goal",
    "set_piece_goal",
    "high_turnover_goal",
    "open_play_goal",
    "penalty",  # a penalty counts as a goal
}
MAX_PLANTED = 6
LAST_MINUTE = 95
HALF_TIME = 45
MIN_GOAL_GAP = 2  # minutes between the windows of two goals for the same side
# Narrowest window (minutes) each kind fits in; the long sequences need two.
MIN_WINDOW: dict[str, int] = {"open_play_goal": 2, "penalty": 2}
_MOMENT_WORD = {
    "red_card": "red card",
    "penalty": "penalty",
    "counter_goal": "goal",
    "set_piece_goal": "goal",
    "high_turnover_goal": "goal",
    "open_play_goal": "goal",
}


def _words(kind: str) -> str:
    return kind.replace("_", " ")


def validate_planted(beats: Sequence[PlantedSpec]) -> list[str]:
    """Plain-English reasons these moments cannot be planted; empty when they can."""
    errors: list[str] = []
    if len(beats) > MAX_PLANTED:
        errors.append(f"There can be at most {MAX_PLANTED} moments, not {len(beats)}.")
    for i, (kind, side, lo, hi) in enumerate(beats, start=1):
        label = f"Moment {i} ({_words(kind)}, {side})"
        if lo < 0 or hi > LAST_MINUTE:
            errors.append(
                f"{label} has a window of {lo}–{hi}′; windows must sit inside 0–{LAST_MINUTE}′."
            )
        elif lo >= hi:
            errors.append(
                f"{label} has a window of {lo}–{hi}′; it must start before it ends."
            )
        elif lo < HALF_TIME < hi:
            errors.append(
                f"{label} has a window of {lo}–{hi}′ that spans half-time; keep it within one half."
            )
        elif hi - lo < MIN_WINDOW.get(kind, 1):
            errors.append(
                f"{label} needs a window of at least {MIN_WINDOW[kind]} minutes, not {hi - lo}."
            )
    for (i, a), (j, b) in itertools.combinations(enumerate(beats, start=1), 2):
        if a[2] < b[3] and b[2] < a[3] and a[2] < a[3] and b[2] < b[3]:
            errors.append(
                f"Moments {i} and {j} have overlapping windows ({a[2]}–{a[3]}′ and {b[2]}–{b[3]}′); "
                "play them one after the other so each fits in its own window."
            )
    for side in ("home", "away"):
        reds = [b for b in beats if b[0] == "red_card" and b[1] == side]
        if len(reds) > 1:
            errors.append(
                f"There can be at most one red card per side; {side} has {len(reds)}."
            )
        goals = sorted(
            (b for b in beats if b[0] in GOAL_KINDS and b[1] == side),
            key=lambda b: b[2:],
        )
        for a, b in itertools.pairwise(goals):
            if b[2] - a[3] < MIN_GOAL_GAP:
                errors.append(
                    f"Two {side} goals ({a[2]}–{a[3]}′ and {b[2]}–{b[3]}′) need windows at least "
                    f"{MIN_GOAL_GAP} minutes apart so a goal sequence fits between them."
                )
    return errors


def final_score(beats: Sequence[PlantedSpec]) -> tuple[int, int]:
    """Home and away goals: only planted goals score (the v1 rule)."""
    return (
        sum(1 for k, s, _, _ in beats if k in GOAL_KINDS and s == "home"),
        sum(1 for k, s, _, _ in beats if k in GOAL_KINDS and s == "away"),
    )


def custom_text(
    home: TeamTactics, away: TeamTactics, beats: Sequence[PlantedSpec]
) -> str:
    """The storyline text of a custom brief, from the moments alone."""
    if not beats:
        return "Custom: no planted moments."
    names = {"home": home.name, "away": away.name}
    parts = [f"{names[s]} {_MOMENT_WORD[k]} {a}–{b}′" for k, s, a, b in beats]
    return "Custom: " + "; ".join(parts)


# Dial bands from the prototype: (high threshold, mid threshold) per dial.
PRESS_BANDS = (0.7, 0.45)
DIRECT_BANDS = (0.65, 0.35)
LINE_BANDS = (0.65, 0.4)

_PRESS = ["press high", "press from a mid shape", "drop off and wait"]
_DIRECT = ["play direct", "mix short and long", "keep the ball patiently"]
_LINE_HOME = ["hold a high line", "hold a mid line", "defend deep"]
_LINE_AWAY = ["defend in a high block", "sit in a mid shape", "sit in a low block"]


def _band(v: float, hi: float, lo: float) -> int:
    return 0 if v >= hi else (1 if v >= lo else 2)


def _team_line(
    name: str,
    formation: str,
    press: float,
    directness: float,
    line: float,
    is_home: bool,
) -> str:
    """Word for word from teamLine in docs/prototype/Main.dc.html (English)."""
    line_words = _LINE_HOME if is_home else _LINE_AWAY
    return (
        f"{name} ({formation}) {_PRESS[_band(press, *PRESS_BANDS)]}, "
        f"{_DIRECT[_band(directness, *DIRECT_BANDS)]} and {line_words[_band(line, *LINE_BANDS)]}."
    )


def brief_text(brief: MatchBrief) -> str:
    h, a = brief.home, brief.away
    return " ".join(
        [
            _team_line(
                h.name,
                h.formation.value,
                h.press.root,
                h.directness.root,
                h.line_height.root,
                True,
            ),
            _team_line(
                a.name,
                a.formation.value,
                a.press.root,
                a.directness.root,
                a.line_height.root,
                False,
            ),
            brief.storyline.text,
        ]
    )


def make_brief(
    home: TeamTactics = DEFAULT_HOME,
    away: TeamTactics = DEFAULT_AWAY,
    storyline_id: str = "late_comeback",
    seed: int = 0,
    planted: Sequence[PlantedSpec] | None = None,
) -> MatchBrief:
    """A brief from tactics and a storyline. `planted` supplies the moments of a custom storyline."""
    if storyline_id == "custom":
        beats = list(planted or [])
        story = Storyline(custom_text(home, away, beats), beats, final_score(beats))
        digest = hashlib.sha256(repr(beats).encode()).hexdigest()[:6]
        match_id = f"m-custom-{seed}-{digest}"
    else:
        story = STORYLINES[storyline_id]
        match_id = f"m-{storyline_id.replace('_', '-')}-{seed}"

    def team(t: TeamTactics, side: str) -> dict[str, object]:
        return {
            "name": t.name,
            "short": t.short,
            "formation": t.formation,
            "press": t.press,
            "directness": t.directness,
            "line_height": t.line_height,
            "players": [p.model_dump(mode="json") for p in make_roster(side, seed)],
        }

    brief = MatchBrief.model_validate(
        {
            "match_id": match_id,
            "seed": seed,
            "home": team(home, "home"),
            "away": team(away, "away"),
            "storyline": {"id": storyline_id, "text": story.text},
            "planted_beats": [
                {
                    "id": f"pb-{i + 1:02d}",
                    "kind": k,
                    "side": s,
                    "minute_from": a,
                    "minute_to": b,
                }
                for i, (k, s, a, b) in enumerate(story.beats)
            ],
        }
    )
    brief.brief_text = brief_text(brief)
    return brief


def random_moments(rng: random.Random, count: int) -> list[PlantedSpec]:
    """Up to `count` random moments that pass validate_planted (fewer if sampling keeps failing)."""
    kinds = sorted(GOAL_KINDS | {"red_card"})
    beats: list[PlantedSpec] = []
    for _ in range(count * 40):
        if len(beats) == count:
            break
        half = rng.choice([(0, HALF_TIME), (HALF_TIME, LAST_MINUTE)])
        width = rng.randint(2, 10)
        lo = rng.randint(half[0], half[1] - width)
        candidate = (rng.choice(kinds), rng.choice(["home", "away"]), lo, lo + width)
        if not validate_planted([*beats, candidate]):
            beats.append(candidate)
    return sorted(beats, key=lambda b: b[2])


def random_brief(seed: int) -> MatchBrief:
    """Random formations and dials plus a preset or 1–3 custom moments; the same seed, the same brief."""
    rng = random.Random(f"random-brief-{seed}")
    formations = sorted(FORMATIONS)

    def tactics(base: TeamTactics) -> TeamTactics:
        return TeamTactics(
            base.name,
            base.short,
            rng.choice(formations),
            round(rng.random(), 2),
            round(rng.random(), 2),
            round(rng.random(), 2),
        )

    home, away = tactics(DEFAULT_HOME), tactics(DEFAULT_AWAY)
    choices = [*sorted(STORYLINES), "custom"]
    story = rng.choice(choices)
    if story == "custom":
        return make_brief(
            home, away, "custom", seed, random_moments(rng, rng.randint(1, 3))
        )
    return make_brief(home, away, story, seed)
