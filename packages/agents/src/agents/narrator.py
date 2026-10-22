"""The Narrator: one beat's fact bundle in, one to three short claims out.

It reads the bundle, never raw events (seam rule 2). The prompt is a versioned file; the few-shot
examples are built from voice/examples.yaml for the beat's kind and mode.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator

from .llm_client import ChatClient
from .structured import Structured, complete_structured

Mode = Literal["fan", "analyst", "producer"]

PROMPT_PATH = Path(__file__).parent / "prompts" / "narrator.v1.md"
EXAMPLES_PATH = Path(__file__).resolve().parents[4] / "voice" / "examples.yaml"
MAX_WORDS = 30
MIN_CLAIMS, MAX_CLAIMS = 1, 3
MIN_EXAMPLES, MAX_EXAMPLES = 4, 6
REGISTER = (
    "live-text football commentary. Present tense. Short: one or two sentences. Team before "
    "player. A number appears only when a fact supplies it."
)
MODE_RULES: Mapping[str, str] = {
    "fan": "fan. What happened and why it matters.",
    "analyst": "analyst. The mechanism: shape, distances, sequences.",
    "producer": "producer. A rundown note (clip window, angle, what to show), not commentary.",
}


class DraftClaim(BaseModel):
    text: str
    fact_ids: list[str] = Field(min_length=1)

    @field_validator("text")
    @classmethod
    def _short(cls, text: str) -> str:
        if len(text.split()) > MAX_WORDS:
            raise ValueError(f"text must be {MAX_WORDS} words or fewer")
        return text.strip()


class NarratorOutput(BaseModel):
    claims: list[DraftClaim] = Field(min_length=MIN_CLAIMS, max_length=MAX_CLAIMS)


@dataclass(frozen=True)
class Revision:
    """The Checker's reasons for the one retry, with the draft they apply to."""

    draft: list[DraftClaim]  # the claims that failed
    reasons: list[str]
    kept: list[str] = field(default_factory=list)  # accepted claims; do not repeat them


def load_examples(path: Path | None = None) -> list[dict[str, Any]]:
    raw: list[dict[str, Any]] = yaml.safe_load(
        (path or EXAMPLES_PATH).read_text("utf-8")
    )
    return [e for e in raw if not e.get("format_only") and e["lang"] == "en"]


def pick_examples(
    examples: list[dict[str, Any]], kind: str, mode: str
) -> list[dict[str, Any]]:
    """Four to six examples for the beat: matching kind and mode first, then the same mode, then
    the same kind. One AMENDED pair is always included, preferring one that matches."""
    plain = [e for e in examples if e.get("amended_from") is None]
    amended = [e for e in examples if e.get("amended_from") is not None]
    ranked = (
        [e for e in plain if e["beat_kind"] == kind and e["mode"] == mode]
        + [e for e in plain if e["mode"] == mode and e["beat_kind"] != kind]
        + [e for e in plain if e["beat_kind"] == kind and e["mode"] != mode]
        + [e for e in plain if e["mode"] != mode and e["beat_kind"] != kind]
    )
    pair = next(
        (e for e in amended if e["beat_kind"] == kind and e["mode"] == mode),
        next(
            (e for e in amended if e["beat_kind"] == kind),
            next((e for e in amended if e["mode"] == mode), amended[0]),
        ),
    )
    room = min(MAX_EXAMPLES - 1, max(MIN_EXAMPLES - 1, len(ranked)))
    return [*ranked[:room], pair]


def format_example(example: dict[str, Any]) -> str:
    facts = "; ".join(f"{f['id']}: {f['display']}" for f in example["facts"])
    lines = [f"Beat: {example['beat_kind']} ({example['mode']})", f"Facts: {facts}"]
    if example.get("amended_from"):
        lines += [
            f"AMENDED. Draft: {example['amended_from']}",
            f"Why it was changed: {example['reason']}",
            f"Final: {example['line']}",
        ]
    else:
        lines.append(f"Line: {example['line']}")
    return "\n".join(lines)


def format_fact(fact: Mapping[str, Any]) -> str:
    shown = " | ".join(fact["display"]["en"])
    scope = fact.get("scope") or {}
    side = f", side {scope['side']}" if scope.get("side") else ""
    return f"- {fact['id']}: {fact['name']} = {fact['value']} (write as: {shown}{side})"


def build_prompt(
    bundle: Mapping[str, Any],
    mode: Mode,
    teams: Mapping[str, str],
    revision: Revision | None = None,
    examples: list[dict[str, Any]] | None = None,
) -> str:
    beat = bundle["beat"]
    picked = pick_examples(
        examples if examples is not None else load_examples(), beat["kind"], mode
    )
    revise = ""
    if revision is not None:
        draft = "\n".join(
            f"- {c.text} (facts: {', '.join(c.fact_ids)})" for c in revision.draft
        )
        reasons = "\n".join(f"- {r}" for r in revision.reasons)
        revise = (
            "\nYour previous draft was rejected by the Checker.\n"
            f"Draft:\n{draft}\nReasons:\n{reasons}\n"
            f"Write {len(revision.draft)} replacement claim"
            f"{'s' if len(revision.draft) != 1 else ''}, one per failed claim in the same order, "
            "so that each reason is fixed. Change only what the reasons require.\n"
        )
        if revision.kept:
            revise += (
                "These claims were accepted; do not repeat them:\n"
                + "\n".join(f"- {t}" for t in revision.kept)
                + "\n"
            )
        revise += "\n"
    values = {
        "min_claims": str(MIN_CLAIMS),
        "max_claims": str(MAX_CLAIMS),
        "max_words": str(MAX_WORDS),
        "register": REGISTER,
        "mode_rule": MODE_RULES[mode],
        "home": teams["home"],
        "away": teams["away"],
        "examples": "\n\n".join(format_example(e) for e in picked),
        "beat_kind": beat["kind"],
        "beat_label": beat["label"],
        "facts": "\n".join(format_fact(f) for f in bundle["facts"]),
        "revision": revise,
    }
    prompt = PROMPT_PATH.read_text("utf-8")
    for key, value in values.items():
        prompt = prompt.replace("{{" + key + "}}", value)
    return prompt


def narrate(
    client: ChatClient,
    bundle: Mapping[str, Any],
    mode: Mode,
    lang: Literal["en"] = "en",
    *,
    teams: Mapping[str, str],
    revise: Revision | None = None,
    max_tokens: int = 700,
) -> Structured[NarratorOutput]:
    """Draft claims for one beat. `revise` carries the Checker's reasons for the one retry."""
    assert lang == "en"  # the Localizer handles the other languages
    prompt = build_prompt(bundle, mode, teams, revise)
    return complete_structured(client, NarratorOutput, prompt, max_tokens=max_tokens)
