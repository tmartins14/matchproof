import re

import pytest
from contracts.models import Event
from intel.labels import LabelContext
from intel.sources import aggregate_label, freeze_frame_label, window_label
from matches import lean

TEAMS = {"home": "Rivermouth", "away": "Ashford Vale"}
# What a viewer never reads in a source label.
MACHINE = re.compile(
    r"1 Hz|samples?\b|seconds? before|\bev-\d|\bagg-|\bt\d{3,}|_", re.IGNORECASE
)


@pytest.fixture(scope="module")
def ctx() -> LabelContext:
    m = lean("red_card_flip", 3)
    return LabelContext(TEAMS, {e.id.root: e for e in m.events}, m.registry)


def kind_of(agg_id: str) -> str:
    return re.sub(r"\d+(_\d+)*", "N", agg_id)


def test_every_aggregate_kind_the_registry_makes_has_a_viewer_label(
    ctx: LabelContext,
) -> None:
    by_kind: dict[str, str] = {}
    for agg_id in ctx.registry.aggregates:
        by_kind.setdefault(kind_of(agg_id), agg_id)
    assert set(by_kind) == {
        "agg-position_samples",
        "agg-running_to_N",
        "agg-momentum_min_N",
        "agg-last_Nm_to_tN",
        "agg-before_ev_N",
        "agg-since_ev_N_to_tN",
    }
    for agg_id in ctx.registry.aggregates:
        label = aggregate_label(agg_id, ctx)
        assert label != "Match data", agg_id
        assert not MACHINE.search(label), (agg_id, label)


def test_known_labels(ctx: LabelContext) -> None:
    assert aggregate_label("agg-before_ev_001484", ctx) == (
        "Play in the 15 minutes before the red card (63′)"
    )
    assert aggregate_label("agg-since_ev_001484_to_t4671_00", ctx) == (
        "Play from the red card (63′) to 77:51"
    )
    assert aggregate_label("agg-last_11m_to_t3103_99", ctx) == (
        "Play in the 11 minutes to 51:43"
    )
    assert aggregate_label("agg-running_to_5", ctx) == "Play up to 5′"
    assert aggregate_label("agg-momentum_min_01", ctx) == "Play from 0:00 to 5:00"
    assert aggregate_label("agg-position_samples", ctx) == (
        "Where the players stood through the match"
    )
    assert aggregate_label("agg-something_new", ctx) == "Match data"


def test_a_goal_anchor_reads_as_the_clubs_goal(ctx: LabelContext) -> None:
    goal = next(
        e
        for e in ctx.events.values()
        if e.type.value == "shot" and e.outcome and e.outcome.value == "goal"
    )
    n = goal.id.root.removeprefix("ev-")
    label = aggregate_label(f"agg-before_ev_{n}", ctx)
    assert label.startswith("Play in the 15 minutes before Rivermouth's goal (")
    assert not MACHINE.search(label)


def test_window_and_freeze_frame_labels(ctx: LabelContext) -> None:
    assert window_label(0.0, 900.0) == "Play from 0:00 to 15:00"
    event: Event = next(iter(ctx.events.values()))
    assert freeze_frame_label(event.id.root, ctx).startswith("Where everyone stood at ")
    assert freeze_frame_label("ev-999999", ctx) == "Where everyone stood"
