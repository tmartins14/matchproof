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


def test_the_shipped_price_table_has_no_values_yet() -> None:
    assert load_prices() == {}
    assert cost_of(USAGE) == NOT_SET


def test_cost_is_tokens_times_price_by_role() -> None:
    out = cost_of(USAGE, PRICES)
    assert out == {
        "currency": "CAD",
        "total": 3.4,
        "by_role": {"narrator": 2.0, "auditor": 1.4},
    }


def test_one_unpriced_deployment_means_no_cost() -> None:
    assert cost_of(USAGE, {"gpt-5-mini": PRICES["gpt-5-mini"]}) == NOT_SET


def test_the_budget_snapshot_splits_input_and_output_and_carries_the_cost() -> None:
    counter = TokenBudget()
    client = MeteredClient(
        FakeChat(['{"a": 1}', '{"a": 1}'], "gpt-5-mini"), "narrator", counter=counter
    )
    client.complete("x")
    client.complete("y")
    snap = counter.snapshot()
    assert snap["by_role"] == {"narrator": 28}  # FakeChat: 10 in, 4 out per call
    assert snap["usage"] == {
        "narrator": {"deployment": "gpt-5-mini", "input": 20, "output": 8}
    }
    assert snap["cost"] == NOT_SET
