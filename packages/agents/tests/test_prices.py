from collections.abc import Mapping

import pytest
from agents.budget import MeteredClient, TokenBudget
from agents.prices import NOT_SET, Price, cost_of, load_prices
from fakes import FakeChat

USAGE = {
    "narrator": {"deployment": "gpt-5-mini", "input": 2_000_000, "output": 500_000},
    "auditor": {"deployment": "judge-grok", "input": 1_000_000, "output": 100_000},
}
PRICES = {
    "gpt-5-mini": Price(0.5, 2.0, "CAD", "https://example.test/prices", "2026-10-23"),
    "judge-grok": Price(1.0, 4.0, "CAD", None, None),
}


def test_the_shipped_price_table_is_complete() -> None:
    prices = load_prices()
    assert prices
    for deployment, price in prices.items():
        assert price.currency, deployment
        assert price.source, deployment
        assert price.as_of, deployment
    assert "judge-mai" not in prices  # bake-off only, left unset


def test_cost_is_tokens_times_price_by_role() -> None:
    out = cost_of(USAGE, PRICES)
    assert out == {
        "currency": "CAD",
        "total": 3.4,
        "by_role": {"narrator": 2.0, "auditor": 1.4},
    }


def test_one_unpriced_deployment_means_no_cost() -> None:
    assert cost_of(USAGE, {"gpt-5-mini": PRICES["gpt-5-mini"]}) == NOT_SET


def _snapshot_after_two_calls() -> dict[str, object]:
    counter = TokenBudget()
    client = MeteredClient(
        FakeChat(['{"a": 1}', '{"a": 1}'], "gpt-5-mini"), "narrator", counter=counter
    )
    client.complete("x")
    client.complete("y")
    return counter.snapshot()


def test_the_budget_snapshot_splits_input_and_output_and_carries_the_cost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table: Mapping[str, Price] = {"gpt-5-mini": PRICES["gpt-5-mini"]}
    monkeypatch.setattr("agents.prices.load_prices", lambda: table)
    snap = _snapshot_after_two_calls()
    assert snap["by_role"] == {"narrator": 28}  # FakeChat: 10 in, 4 out per call
    assert snap["usage"] == {
        "narrator": {"deployment": "gpt-5-mini", "input": 20, "output": 8}
    }
    # (20 * 0.5 + 8 * 2.0) / 1e6
    assert snap["cost"] == {
        "currency": "CAD",
        "total": 0.000026,
        "by_role": {"narrator": 0.000026},
    }


def test_the_budget_snapshot_says_prices_not_set_for_an_unpriced_deployment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("agents.prices.load_prices", dict)
    assert _snapshot_after_two_calls()["cost"] == NOT_SET
