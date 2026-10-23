"""The Narrator: one beat's fact bundle in, one to three short claims out.

It reads the bundle, never raw events (seam rule 2). The prompt is a versioned file; the few-shot
examples are built from voice/examples.yaml for the beat's kind and mode.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal

import yaml
from contracts.paths import runtime_root
from intel.labels import say
from intel.voice_lint import lint, load_rules
from pydantic import BaseModel, Field, field_validator

from .llm_client import ChatClient
from .structured import Structured, complete_structured

Mode = Literal["fan", "analyst", "producer"]

PROMPT_PATH = (
    Path(__file__).parent / "prompts" / "narrator.v2.md"
)  # v1 is kept for the record
EXAMPLES_PATH = runtime_root() / "voice" / "examples.yaml"
MAX_WORDS = 30
MIN_CLAIMS, MAX_CLAIMS = 1, 3
MIN_EXAMPLES, MAX_EXAMPLES = 4, 6
REGISTER = (
    "live-text football commentary. Present tense. Short: one or two sentences. Team before "
    "player. A number appears only when a fact supplies it."
)
MODE_CLAIMS: Mapping[str, tuple[int, int]] = {
    "fan": (1, 2),
    "analyst": (1, 3),
    "producer": (1, 2),
}
NUMBER_RULES: Mapping[str, str] = {
    "fan": 'At most two numbers in a claim, and never a zero count ("0 passes", "0 attackers"): '
    "leave that fact out instead.",
    "analyst": "Use at most three numbers in a claim and no zero counts. xG and positional "
    "numbers are welcome here.",
    "producer": "Use at most two numbers in a claim, and no zero counts.",
}
NUMBER_CHECKS: Mapping[str, str] = {
    "fan": "More than two: cut it down to two.",
    "analyst": "More than three: cut it down to three.",
    "producer": "More than two: cut it down to two.",
}
MODE_RULES: Mapping[str, str] = {
    "fan": "fan. What happened and why it matters.",
    "analyst": "analyst. The mechanism: shape, distances, sequences.",
    "producer": "producer. A rundown note (clip window, angle, what to show), not commentary.",
}


def normalise_punctuation(text: str) -> str:
    """Punctuation only: an em dash becomes a comma, and typographic hyphens and apostrophes become
    plain ones, so names still match and the voice lint is not tripped by a character."""
    text = re.sub(r"\s*—\s*", ", ", text)
    return text.replace("\u2011", "-").replace("\u2019", "'").strip()


class DraftClaim(BaseModel):
    text: str
    fact_ids: list[str] = Field(min_length=1)

    @field_validator("text")
    @classmethod
    def _short(cls, text: str) -> str:
        if len(text.split()) > MAX_WORDS:
            raise ValueError(f"text must be {MAX_WORDS} words or fewer")
        return normalise_punctuation(text)


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
    rules = load_rules()
    return [
        e
        for e in raw
        if not e.get("format_only")
        and e["lang"] == "en"
        # A line that breaks a voice rule, even a warning, would teach the model to break it.
        and not lint(e["line"], "narration", rules)
    ]


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
    kind = example["beat_kind"].replace("_", " ")
    lines = [f"Beat: {kind} ({example['mode']})", f"Facts: {facts}"]
    if example.get("amended_from"):
        lines += [
            f"AMENDED. Draft: {example['amended_from']}",
            f"Why it was changed: {example['reason']}",
            f"Final: {example['line']}",
        ]
    else:
        lines.append(f"Line: {example['line']}")
    return "\n".join(lines)


def format_fact(fact: Mapping[str, Any], teams: Mapping[str, str]) -> str:
    """One fact as the Narrator sees it: id, what it measures, the words it may be written as."""
    shown = " / ".join(say(fact["value"], fact["display"]["en"], teams))
    scope = fact.get("scope") or {}
    side = f" | {teams[scope['side']]}" if scope.get("side") else ""
    return f"- {fact['id']} | {fact['label']} | write as: {shown}{side}"


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
        "min_claims": str(MODE_CLAIMS[mode][0]),
        "max_claims": str(MODE_CLAIMS[mode][1]),
        "plural": "" if MODE_CLAIMS[mode][1] == 1 else "s",
        "number_rule": NUMBER_RULES[mode],
        "number_check": NUMBER_CHECKS[mode],
        "max_words": str(MAX_WORDS),
        "register": REGISTER,
        "mode_rule": MODE_RULES[mode],
        "home": teams["home"],
        "away": teams["away"],
        "examples": "\n\n".join(format_example(e) for e in picked),
        "beat_kind": beat["kind"].replace("_", " "),
        "beat_label": beat["label"],
        "facts": "\n".join(format_fact(f, teams) for f in bundle["facts"]),
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
    out = complete_structured(client, NarratorOutput, prompt, max_tokens=max_tokens)
    keep = MODE_CLAIMS[mode][
        1
    ]  # a mode's claim limit is enforced here, not left to the model
    if len(out.value.claims) > keep:
        out = replace(out, value=NarratorOutput(claims=out.value.claims[:keep]))
    return out
