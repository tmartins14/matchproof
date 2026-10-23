"""The judge pick rule and the models.yaml edit. In code, not by hand."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

BAD_TOTAL = 38  # bad claims in evals/adversarial/claims.yaml
GOOD_TOTAL = 14  # good claims in the same file
MIN_CAUGHT = 35  # of BAD_TOTAL
MAX_GOOD_BLOCKED = 1  # of GOOD_TOTAL
MAX_P90_MS = 4000
FALLBACK_DEPLOYMENT = "gpt-5-mini"
RULE_TEXT = (
    f"at least {MIN_CAUGHT} of {BAD_TOTAL} bad claims caught, at most {MAX_GOOD_BLOCKED} of {GOOD_TOTAL} good claims "
    f"blocked, judge p90 at most {MAX_P90_MS / 1000:g} s; highest catch count wins, then lower p90"
)


@dataclass(frozen=True)
class Score:
    deployment: str
    caught: int
    good_blocked: int
    p90_ms: int


@dataclass(frozen=True)
class Pick:
    deployment: str
    fallback: bool
    reason: str


def qualifies(s: Score) -> bool:
    return (
        s.caught >= MIN_CAUGHT
        and s.good_blocked <= MAX_GOOD_BLOCKED
        and s.p90_ms <= MAX_P90_MS
    )


def pick_judge(scores: list[Score]) -> Pick:
    """The qualifying candidate with the most bad claims caught, then the lower p90; otherwise the
    fallback deployment with the judge prompt."""
    ok = sorted(
        (s for s in scores if qualifies(s)), key=lambda s: (-s.caught, s.p90_ms)
    )
    if ok:
        best = ok[0]
        return Pick(
            best.deployment,
            False,
            f"{best.deployment} caught {best.caught}/{BAD_TOTAL}, blocked {best.good_blocked}/{GOOD_TOTAL} good, "
            f"p90 {best.p90_ms / 1000:.1f} s",
        )
    return Pick(
        FALLBACK_DEPLOYMENT,
        True,
        "no candidate met the rule, so the fallback judge is used: " + RULE_TEXT,
    )


def set_active_judge(models_path: Path, deployment: str) -> None:
    """Rewrite the `judge:` block of models.yaml with the settings of `deployment`, keeping the
    comments in the rest of the file."""
    text = models_path.read_text("utf-8")
    data: dict[str, Any] = yaml.safe_load(text)
    entries = [*data["judge_candidates"], data["judge_fallback"]]
    entry = next(e for e in entries if e["deployment"] == deployment)
    block = "judge:\n" + "".join(f"  {k}: {v}\n" for k, v in entry.items())
    new = re.sub(r"^judge:\n(?:[ \t]+.*\n)+", block, text, count=1, flags=re.MULTILINE)
    models_path.write_text(new, "utf-8")
