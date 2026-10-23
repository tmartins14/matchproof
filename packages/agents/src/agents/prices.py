"""What model tokens cost, from config/prices.yaml. Never guesses: no price, no cost."""

from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

PRICES_PATH = Path(__file__).resolve().parents[2] / "config" / "prices.yaml"
NOT_SET = "prices not set"


@dataclass(frozen=True)
class Price:
    input_per_million: float
    output_per_million: float
    currency: str
    source: str | None
    as_of: str | None


@lru_cache(maxsize=1)
def load_prices() -> Mapping[str, Price]:
    """The deployments whose input price, output price and currency are all filled in."""
    raw: dict[str, dict[str, Any]] = (
        yaml.safe_load(PRICES_PATH.read_text("utf-8")) or {}
    )
    out: dict[str, Price] = {}
    for deployment, p in raw.items():
        if (
            p.get("input_per_million") is not None
            and p.get("output_per_million") is not None
            and p.get("currency")
        ):
            out[deployment] = Price(
                float(p["input_per_million"]),
                float(p["output_per_million"]),
                str(p["currency"]),
                p.get("source"),
                str(p["as_of"]) if p.get("as_of") is not None else None,
            )
    return out


def cost_of(
    usage: Mapping[str, Mapping[str, Any]], prices: Mapping[str, Price] | None = None
) -> dict[str, Any] | str:
    """Cost by role for `usage` ({role: {deployment, input, output}}), or "prices not set" when any
    deployment used has no price. All roles must be in one currency."""
    table = load_prices() if prices is None else prices
    by_role: dict[str, float] = {}
    currencies: set[str] = set()
    for role, u in usage.items():
        price = table.get(str(u["deployment"]))
        if price is None:
            return NOT_SET
        currencies.add(price.currency)
        by_role[role] = (
            u["input"] * price.input_per_million
            + u["output"] * price.output_per_million
        ) / 1_000_000
    if len(currencies) > 1:
        return NOT_SET
    return {
        "currency": next(iter(currencies), None),
        "total": round(sum(by_role.values()), 6),
        "by_role": {r: round(c, 6) for r, c in by_role.items()},
    }
