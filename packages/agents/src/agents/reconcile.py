"""Number reconciliation: every number in a claim must come from a fact it cites (seam rule 4).

Pure Python, no model. A number matches when it is an exact display rendering of a cited fact, or
when it has the same numeric part and a compatible unit word ("64 per cent" against "64%").
"""

import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import yaml
from contracts.models import Fact
from intel.voice_lint import numbers_in

COMPARATIVES_PATH = Path(__file__).resolve().parents[4] / "voice" / "comparatives.yaml"
COMPARISON_FACTS = (
    "change",
    "before",
)  # a fact whose name has one of these holds a comparison
SCORE_FACTS = ("score_after(", "lead(")

_PART_RE = re.compile(r"(\d+(?:[.,]\d+)*)\s*(%|′|'|per cent|[^\W\d_]+)?", re.IGNORECASE)
_UNIT_ALIASES = {
    "%": "pct",
    "per cent": "pct",
    "percent": "pct",
    "m": "m",
    "metre": "m",
    "metres": "m",
    "meter": "m",
    "meters": "m",
    "s": "s",
    "second": "s",
    "seconds": "s",
    "′": "min",
    "'": "min",
    "min": "min",
    "minute": "min",
    "minutes": "min",
}
_ORDINALS = frozenset({"st", "nd", "rd", "th"})


@dataclass(frozen=True)
class Reading:
    """A number as written: its value and the unit word after it, if any (canonical form)."""

    value: Decimal
    unit: str | None


@dataclass(frozen=True)
class NumberMatch:
    as_written: str
    fact_id: str


@dataclass
class Reconciliation:
    ok: bool
    numbers: list[NumberMatch] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


def _unit(word: str | None) -> str | None:
    if word is None:
        return None
    low = word.lower()
    if low in _ORDINALS:
        return None
    if low in _UNIT_ALIASES:
        return _UNIT_ALIASES[low]
    return low[:-1] if low.endswith("s") and len(low) > 3 else low


def readings(text: str) -> list[Reading]:
    """Every number in `text` with the unit word that follows it."""
    out: list[Reading] = []
    for m in _PART_RE.finditer(text):
        raw = m.group(1).replace(",", ".")
        out.append(Reading(Decimal(raw).normalize(), _unit(m.group(2))))
    return out


def _compatible(claimed: Reading, shown: Reading) -> bool:
    if claimed.value != shown.value:
        return False
    return claimed.unit is None or shown.unit is None or claimed.unit == shown.unit


def _matches(token_at: str, token: Reading, rendering: str) -> bool:
    """`token_at` is the claim text from the number onward."""
    if token_at.startswith(rendering):
        return True
    return any(_compatible(token, shown) for shown in readings(rendering))


@lru_cache(maxsize=1)
def comparatives() -> tuple[re.Pattern[str], ...]:
    """One whole-word pattern per comparison word or phrase in voice/comparatives.yaml."""
    words: list[str] = yaml.safe_load(COMPARATIVES_PATH.read_text(encoding="utf-8"))
    return tuple(
        re.compile(
            rf"(?<![\w-]){re.escape(w).replace(r'\ ', r'\s+')}(?![\w-])", re.IGNORECASE
        )
        for w in words
    )


def comparison_words(text: str) -> list[str]:
    """The comparison words in `text`, as written, once each in order of appearance."""
    found = sorted(
        (m.start(), m.group(0).lower())
        for pattern in comparatives()
        for m in pattern.finditer(text)
    )
    return list(dict.fromkeys(word for _, word in found))


def holds_comparison(fact: Fact) -> bool:
    return fact.name.startswith(SCORE_FACTS) or any(
        word in fact.name for word in COMPARISON_FACTS
    )


def reconcile(
    text: str,
    fact_ids: list[str],
    bundle: Mapping[str, Fact],
    names: Collection[str] = (),
) -> Reconciliation:
    """Check `text` against the facts it cites. `bundle` is the beat's facts by id. `names` are the
    roster's player names: one that appears in the text must be a cited fact's value."""
    reasons: list[str] = []
    if not fact_ids:
        reasons.append("The claim cites no facts.")
    unknown = [fid for fid in fact_ids if fid not in bundle]
    for fid in unknown:
        reasons.append(f"Cited fact {fid} is not in the beat's fact bundle.")
    cited = [bundle[fid] for fid in fact_ids if fid in bundle]
    matched: list[NumberMatch] = []
    cursor = 0
    for token in numbers_in(text):
        start = text.find(token, cursor)
        cursor = start + len(token)
        token_at = text[start:]
        token_reading = readings(token_at)[0]
        # The claim's own unit word counts too: "64 per cent" is written as "64" plus a word.
        found = next(
            (
                f
                for f in cited
                if any(_matches(token_at, token_reading, r) for r in f.display.en)
            ),
            None,
        )
        if found is None:
            reasons.append(
                f'The number "{token}" matches no display rendering of the cited facts.'
            )
        else:
            matched.append(NumberMatch(token, found.id.root))
    words = comparison_words(text)
    if words and not any(holds_comparison(f) for f in cited):
        for word in words[:3]:
            reasons.append(f"'{word}' compares, but no before or change fact is cited.")
    named = {f.value for f in cited if isinstance(f.value, str)}
    for name in sorted(names):
        if (
            re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", text)
            and name not in named
        ):
            reasons.append(f'The player "{name}" is not named by any cited fact.')
    return Reconciliation(not reasons, matched, reasons)
