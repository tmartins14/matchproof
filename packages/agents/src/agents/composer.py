"""The Composer: a free-text brief in, a validated MatchBrief out.

The model proposes tactics and planted moments; code decides what is allowed. Whatever the model
returns passes the same checks a hand-written brief passes (`sim.brief.validate_planted` and the
MatchBrief schema) before it reaches the generator. On errors the model gets one retry with them;
after that the valid part of its answer is kept and the rest is dropped with a warning. The brief
text shown to the user is the deterministic template applied to the result, never model prose.
"""

from dataclasses import dataclass, replace
from pathlib import Path

from contracts.models import MatchBrief
from pydantic import BaseModel
from sim.brief import (
    DEFAULT_AWAY,
    DEFAULT_HOME,
    STORYLINES,
    PlantedSpec,
    TeamTactics,
    make_brief,
    validate_planted,
)
from sim.tactics import FORMATIONS

from .llm_client import ChatClient
from .structured import StructuredOutputError, complete_structured

PROMPT_PATH = Path(__file__).parent / "prompts" / "composer.v1.md"
MAX_TEXT_CHARS = 600
MOMENT_KINDS = frozenset(
    {
        "counter_goal",
        "set_piece_goal",
        "high_turnover_goal",
        "open_play_goal",
        "penalty",
        "red_card",
    }
)
SIDES = frozenset({"home", "away"})
DIALS = ("press", "directness", "line_height")


class TeamAnswer(BaseModel):
    formation: str
    press: float
    directness: float
    line_height: float


class MomentAnswer(BaseModel):
    kind: str
    side: str
    minute_from: int
    minute_to: int


class ComposerAnswer(BaseModel):
    """What the model returns. Types are loose on purpose: the rules live in `check`."""

    home: TeamAnswer
    away: TeamAnswer
    storyline: str
    moments: list[MomentAnswer] = []


@dataclass(frozen=True)
class Composed:
    brief: MatchBrief
    brief_text: str
    warnings: list[str]
    tokens: int = 0


def check(answer: ComposerAnswer) -> list[str]:
    """Every way the answer breaks the rules, in plain English. Empty when it is usable as is."""
    errors: list[str] = []
    for side, team in (("home", answer.home), ("away", answer.away)):
        if team.formation not in FORMATIONS:
            errors.append(
                f"The {side} formation {team.formation!r} is not one of {sorted(FORMATIONS)}."
            )
        for dial in DIALS:
            value = getattr(team, dial)
            if not 0.0 <= value <= 1.0:
                errors.append(f"The {side} {dial} is {value}; it must be from 0 to 1.")
    known = {*STORYLINES, "custom"}
    if answer.storyline not in known:
        errors.append(
            f"The storyline {answer.storyline!r} is not one of {sorted(known)}."
        )
    elif answer.storyline != "custom" and answer.moments:
        errors.append(
            "A preset storyline takes no moments; use storyline custom to plant them."
        )
    for i, m in enumerate(answer.moments, start=1):
        if m.kind not in MOMENT_KINDS:
            errors.append(f"Moment {i} has an unknown kind {m.kind!r}.")
        if m.side not in SIDES:
            errors.append(f"Moment {i} has an unknown side {m.side!r}.")
    if not errors and answer.storyline == "custom":
        errors.extend(validate_planted(specs(answer.moments)))
    return errors


def specs(moments: list[MomentAnswer]) -> list[PlantedSpec]:
    return [(m.kind, m.side, m.minute_from, m.minute_to) for m in moments]


def _tactics(
    base: TeamTactics, team: TeamAnswer, side: str, warnings: list[str]
) -> TeamTactics:
    formation = team.formation
    if formation not in FORMATIONS:
        warnings.append(
            f"Could not use the {side} formation {formation!r}; kept {base.formation}."
        )
        formation = base.formation
    dials: dict[str, float] = {}
    for dial in DIALS:
        value = getattr(team, dial)
        dials[dial] = min(1.0, max(0.0, value))
        if dials[dial] != value:
            warnings.append(f"The {side} {dial} was {value}; moved to {dials[dial]}.")
    return replace(base, formation=formation, **dials)


def repair(answer: ComposerAnswer, seed: int) -> tuple[MatchBrief, list[str]]:
    """The valid part of an answer as a brief, with a warning for each thing dropped or changed."""
    warnings: list[str] = []
    home = _tactics(DEFAULT_HOME, answer.home, "home", warnings)
    away = _tactics(DEFAULT_AWAY, answer.away, "away", warnings)
    story = answer.storyline
    if story not in STORYLINES and story != "custom":
        warnings.append(
            f"Did not recognise the storyline {story!r}; planted only the moments given."
        )
        story = "custom"
    if story != "custom" and answer.moments:
        warnings.append("Planted the moments and left out the preset storyline.")
        story = "custom"
    if story != "custom":
        return make_brief(home, away, story, seed), warnings
    kept: list[PlantedSpec] = []
    for i, m in enumerate(answer.moments, start=1):
        spec = (m.kind, m.side, m.minute_from, m.minute_to)
        if m.kind not in MOMENT_KINDS or m.side not in SIDES:
            warnings.append(
                f"Left out moment {i}: {m.kind!r} for {m.side!r} is not a moment I can plant."
            )
            continue
        problems = validate_planted([*kept, spec])
        if problems:
            warnings.append(
                f"Left out moment {i} ({m.kind.replace('_', ' ')}, {m.side}, {m.minute_from}–{m.minute_to}′): {problems[0]}"
            )
            continue
        kept.append(spec)
    return make_brief(home, away, "custom", seed, kept), warnings


def _prompt(text: str) -> str:
    values = {
        "home": DEFAULT_HOME.name,
        "away": DEFAULT_AWAY.name,
        "formations": ", ".join(sorted(FORMATIONS)),
        "storylines": ", ".join(sorted(STORYLINES)),
        "text": text,
    }
    prompt = PROMPT_PATH.read_text("utf-8")
    for key, value in values.items():
        prompt = prompt.replace("{{" + key + "}}", value)
    return prompt


def compose(client: ChatClient, text: str, seed: int = 0) -> Composed:
    """Turn a free-text brief into a validated MatchBrief. LlmError from the client propagates."""
    prompt = _prompt(text.strip()[:MAX_TEXT_CHARS])
    tokens = 0
    answer: ComposerAnswer | None = None
    errors: list[str] = []
    for attempt in (1, 2):
        ask = prompt
        if errors:
            ask += (
                "\n\nYour previous reply broke these rules:\n"
                + "\n".join(f"- {e}" for e in errors)
                + "\n\nReply again with corrected JSON only."
            )
        try:
            out = complete_structured(client, ComposerAnswer, ask, max_tokens=700)
        except StructuredOutputError:
            errors = ["Your reply was not valid JSON for the schema."]
            continue
        tokens += out.input_tokens + out.output_tokens
        answer = out.value
        errors = check(answer)
        if not errors:
            brief, warnings = repair(answer, seed)  # a clean answer repairs to itself
            return Composed(brief, brief.brief_text or "", warnings, tokens)
    if answer is None:
        brief = make_brief(DEFAULT_HOME, DEFAULT_AWAY, "custom", seed, [])
        return Composed(
            brief,
            brief.brief_text or "",
            [
                "Could not read the composer's answer; kept the default tactics and planted nothing."
            ],
            tokens,
        )
    brief, warnings = repair(answer, seed)
    return Composed(brief, brief.brief_text or "", warnings, tokens)
