import pytest
from sim.calibrate import collect, evaluate, format_table, load_targets, parse_seeds

TARGETS = load_targets()


def check(seeds: list[int]) -> None:
    rows = evaluate(collect(seeds), TARGETS)
    failed = [r for r in rows if not r.ok]
    assert not failed, "\n" + format_table(rows)


def test_targets_are_provisional_and_unsourced() -> None:
    assert len(TARGETS) == 12
    assert all(t.status == "provisional" and t.source == "TBD" for t in TARGETS)


def test_parse_seeds() -> None:
    assert parse_seeds("1-4") == [1, 2, 3, 4]
    assert parse_seeds("1,3,5-6") == [1, 3, 5, 6]


def test_calibration_seeds_1_to_4() -> None:
    check([1, 2, 3, 4])


@pytest.mark.slow
def test_calibration_seeds_1_to_8() -> None:
    check(parse_seeds("1-8"))
