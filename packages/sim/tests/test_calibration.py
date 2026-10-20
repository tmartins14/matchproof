from functools import cache
from statistics import pstdev

import pytest
from sim.calibrate import (
    MEAN_TOLERANCE,
    collect,
    evaluate,
    format_table,
    load_targets,
    parse_seeds,
    run_limits,
)

TARGETS = load_targets()
BACK_LINE_GAIN_M = (
    5.0  # in-possession back line is at least this much higher than out of possession
)
LENGTH_GAIN_M = 8.0  # out-of-possession team length is at least this much shorter than in possession


@cache
def values(seeds: tuple[int, ...]) -> dict[str, list[float]]:
    return collect(list(seeds))


def check(seeds: list[int]) -> None:
    rows = evaluate(values(tuple(seeds)), TARGETS)
    failed = [r for r in rows if not r.ok]
    assert not failed, "\n" + format_table(rows)


def test_every_target_has_a_source_and_status() -> None:
    assert len(TARGETS) == 17
    for t in TARGETS:
        assert t.status in {"sourced", "derived", "provisional"}
        assert t.source and t.source != "TBD"
    assert {t.id for t in TARGETS if t.reference_mean is None} == {
        "progressive_pass_share",
        "back_line_height_in",
        "compactness_out",
    }


def test_reference_means_sit_inside_their_bands() -> None:
    for t in TARGETS:
        if t.reference_mean is not None:
            assert t.band[0] <= t.reference_mean <= t.band[1], t.id
    assert MEAN_TOLERANCE == 0.12


def test_parse_seeds() -> None:
    assert parse_seeds("1-4") == [1, 2, 3, 4]
    assert parse_seeds("1,3,5-6") == [1, 3, 5, 6]


def test_calibration_seeds_1_to_4() -> None:
    check([1, 2, 3, 4])


def test_every_single_run_in_seeds_1_to_4_is_inside_its_limits() -> None:
    v = values((1, 2, 3, 4))
    for t in TARGETS:
        lo, hi = run_limits(t)
        bad = [x for x in v[t.id] if not lo <= x <= hi]
        assert not bad, f"{t.id}: runs {bad} outside {lo:g} to {hi:g}"


def test_only_xg_per_shot_has_a_match_band() -> None:
    assert {t.id: t.match_band for t in TARGETS if t.match_band} == {
        "xg_per_shot": (0.04, 0.25)
    }
    assert next(t for t in TARGETS if t.id == "xg_per_shot").band == (0.08, 0.15)


def test_out_of_possession_area_varies_across_runs(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Run medians of team length are all within float noise of each other (the block only changes shape
    on a red card, a late score or a press dial), so the frame-level check lives in test_positions."""
    v = values((1, 2, 3, 4))
    spread = {k: pstdev(v[k]) for k in ("team_length_out", "compactness_out")}
    with capsys.disabled():
        print(f"\nrun-median std over {len(v['team_length_out'])} runs: {spread}")
    assert spread["compactness_out"] > 0.1


def test_shape_rules_seeds_1_to_4() -> None:
    v = values((1, 2, 3, 4))
    assert min(v["back_line_gain"]) >= BACK_LINE_GAIN_M
    assert min(v["length_gain"]) >= LENGTH_GAIN_M


@pytest.mark.slow
def test_calibration_seeds_1_to_8() -> None:
    check(parse_seeds("1-8"))
