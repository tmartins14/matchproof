"""Storylines, tactics and the tactics-to-brief template (ADR 0004)."""

from dataclasses import dataclass

from contracts.models import MatchBrief

from .roster import make_roster


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
) -> MatchBrief:
    story = STORYLINES[storyline_id]

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
            "match_id": f"m-{storyline_id.replace('_', '-')}-{seed}",
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
