"""The fact registry: facts keyed by deterministic ids derived from their names."""

import re
from collections.abc import Sequence

from contracts.models import Fact

from .display import Value, render

EXTRACTOR_VERSION = "1"  # bump when an extractor's definitions change


def slug(name: str) -> str:
    """Lower-case the name and collapse everything outside a-z, 0-9 and _ into single hyphens."""
    return re.sub(r"[^a-z0-9_]+", "-", name.lower()).strip("-")


def fact_id(name: str) -> str:
    """The id of the fact called `name`; the same name always gives the same id."""
    return "fx-" + slug(name)


def build_fact(
    name: str,
    value: Value,
    unit: str,
    source_ids: Sequence[str],
    extractor: str,
    scope: dict[str, object] | None = None,
    display: dict[str, list[str]] | None = None,
) -> Fact:
    """A schema-valid Fact. Floats are stored to four decimals; display comes from intel.display."""
    stored: Value = round(value, 4) if isinstance(value, float) else value
    raw: dict[str, object] = {
        "id": fact_id(name),
        "name": name,
        "value": stored,
        "display": display
        or {"en": render(stored, unit, "en"), "es": render(stored, unit, "es")},
        "source_ids": sorted(set(source_ids)),
        "extractor": {"name": extractor, "version": EXTRACTOR_VERSION},
    }
    if unit:
        raw["unit"] = unit
    if scope:
        raw["scope"] = scope
    return Fact.model_validate(raw)


class FactRegistry:
    """Every fact computed for a match, plus the aggregate names that facts may cite as sources."""

    def __init__(self) -> None:
        self._facts: dict[str, Fact] = {}
        self._by_name: dict[str, str] = {}
        self.aggregates: dict[str, str] = {}

    def add(self, fact: Fact) -> bool:
        """Add a fact. True if it is new; False if an identical fact is already there.

        The same name with a different value (or sources, display) is an error, as is an id collision.
        """
        fid = fact.id.root
        existing = self._facts.get(fid)
        if existing is not None:
            if existing != fact:
                raise ValueError(f"conflicting fact for {fact.name!r}: {fid}")
            return False
        self._facts[fid] = fact
        self._by_name[fact.name] = fid
        return True

    def get(self, fact_id: str) -> Fact:
        return self._facts[fact_id]

    def by_name(self, name: str) -> Fact:
        return self._facts[self._by_name[name]]

    def has_name(self, name: str) -> bool:
        return name in self._by_name

    def all(self) -> list[Fact]:
        """All facts in id order, so the same match always lists the same way."""
        return [self._facts[k] for k in sorted(self._facts)]

    def register_aggregate(self, agg_id: str, description: str) -> None:
        if not agg_id.startswith("agg-"):
            raise ValueError(f"aggregate ids start with agg-: {agg_id}")
        self.aggregates[agg_id] = description

    def __len__(self) -> int:
        return len(self._facts)

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, FactRegistry)
            and self.all() == other.all()
            and self.aggregates == other.aggregates
        )

    __hash__ = None  # type: ignore[assignment]
