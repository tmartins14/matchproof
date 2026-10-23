"""The score: goals so far, and how to say it."""

from collections.abc import Iterable, Mapping

from contracts.models import Event

from .football import SIDES


def is_goal(e: Event) -> bool:
    return (
        e.type.value == "shot" and e.outcome is not None and e.outcome.value == "goal"
    )


def match_score(events: Iterable[Event], t: float | None = None) -> tuple[int, int]:
    """(home, away) goals scored at match second `t` (inclusive); the final score without `t`."""
    goals = {side: 0 for side in SIDES}
    for e in events:
        if is_goal(e) and (t is None or e.t.root <= t):
            goals[e.side.value] += 1
    return goals["home"], goals["away"]


def score_text(home: int, away: int, teams: Mapping[str, str]) -> str:
    """Home side first, as on a scoreboard: Rivermouth 1–0 Ashford Vale."""
    return f"{teams['home']} {home}–{away} {teams['away']}"


def lead_text(home: int, away: int, teams: Mapping[str, str]) -> str:
    if home == away:
        return "level"
    return f"{teams['home' if home > away else 'away']} lead"
