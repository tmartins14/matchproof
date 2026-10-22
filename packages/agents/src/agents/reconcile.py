"""Number reconciliation: every number in a claim must come from a fact it cites (seam rule 4).

Pure Python, no model. A number matches when it is an exact display rendering of a cited fact, or
when it has the same numeric part and a compatible unit word ("64 per cent" against "64%").
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal

from contracts.models import Fact
from intel.voice_lint import numbers_in

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


def reconcile(
    text: str, fact_ids: list[str], bundle: Mapping[str, Fact]
) -> Reconciliation:
    """Check `text` against the facts it cites. `bundle` is the beat's facts by id."""
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
    return Reconciliation(not reasons, matched, reasons)
