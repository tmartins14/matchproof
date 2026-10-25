import re

import pytest
from contracts.models import Fact
from intel.desk import (
    BUCKET_COUNT,
    attacking_actions,
    bucket_number,
    is_desk_fact,
    minute_mark,
)
from intel.engine import FactEngine
from intel.labels import LabelContext, label_for
from intel.since import last_minutes, since
from matches import lean, match

STORIES = [("red_card_flip", 3), ("late_comeback", 1)]
TEAMS = {"home": "Rivermouth", "away": "Ashford Vale"}
RAW_TIME = re.compile(r"t\d+\.\d+|match time")


def named(facts: list[Fact], prefix: str) -> dict[str, Fact]:
    return {f.name: f for f in facts if f.name.startswith(prefix)}


@pytest.mark.parametrize(("story", "seed"), STORIES)
def test_running_totals_equal_the_windows_they_cover(story: str, seed: int) -> None:
    facts = lean(story, seed).registry.all()
    by_name = {f.name: f for f in facts}
    # min-09 ends with the first half and min-18 with the second, where a window ends too.
    for number, wins in ((9, ("win-01", "win-02", "win-03")), (18, None)):
        for side in ("home", "away"):
            for metric in ("shots", "xg"):
                total = by_name[f"{metric}({side}, to {minute_mark(number)}′)"].value
                names = (
                    [f"{metric}({side}, {w})" for w in wins]
                    if wins
                    else [f"{metric}({side}, win-0{n})" for n in range(1, 7)]
                )
                assert total == pytest.approx(
                    sum(float(by_name[n].value) for n in names), abs=1e-3
                ), (side, metric, number)
    for side in ("home", "away"):
        full = by_name[f"possession_share({side}, to 90′)"]
        assert full.value == by_name[f"possession_share({side}, match)"].value
        assert [s.root for s in full.source_ids] == [f"win-0{n}" for n in range(1, 7)]


@pytest.mark.parametrize(("story", "seed"), STORIES)
def test_running_totals_only_grow_and_cite_their_sources(story: str, seed: int) -> None:
    m = lean(story, seed)
    for side in ("home", "away"):
        for metric in ("shots", "shots_on_target", "xg"):
            values = [
                float(
                    m.registry.by_name(f"{metric}({side}, to {minute_mark(n)}′)").value
                )
                for n in range(1, BUCKET_COUNT + 1)
            ]
            assert values == sorted(values), (side, metric)
    known = set(m.registry.aggregates) | {f"win-0{n}" for n in range(1, 7)}
    for fact in m.registry.all():
        if is_desk_fact(fact):
            assert {s.root for s in fact.source_ids} <= known, fact.name


@pytest.mark.parametrize(("story", "seed"), STORIES)
def test_momentum_is_in_range_for_18_buckets_and_its_sign_matches_the_shares(
    story: str, seed: int
) -> None:
    m = lean(story, seed)
    buckets: dict[int, list] = {n: [] for n in range(1, BUCKET_COUNT + 1)}
    for e in m.events:
        buckets[bucket_number(e.period.value, e.t.root)].append(e)
    momentum = named(m.registry.all(), "momentum(")
    assert len(momentum) == BUCKET_COUNT == 18
    for n in range(1, BUCKET_COUNT + 1):
        fact = momentum[f"momentum(min-{n:02d})"]
        assert fact.unit is not None and fact.unit.value == "pp"
        value = float(fact.value)
        assert -100.0 <= value <= 100.0
        home = attacking_actions(buckets[n], "home")
        away = attacking_actions(buckets[n], "away")
        if home + away == 0:
            assert value == 0.0
        else:
            assert value == pytest.approx(
                100.0 * (home - away) / (home + away), abs=1e-3
            )
            assert (value > 0) - (value < 0) == (home > away) - (home < away)


@pytest.mark.parametrize(("story", "seed"), STORIES)
def test_live_equals_batch_for_running_totals_and_momentum(
    story: str, seed: int
) -> None:
    m = match(story, seed)
    engine = FactEngine()
    emitted: dict[str, float] = {}
    for item in m.stream:
        for fact in engine.push(item):
            if is_desk_fact(fact):
                emitted[fact.name] = item.t.root
    engine.finish()
    desk = [f for f in engine.registry.all() if is_desk_fact(f)]
    assert len(desk) > 150
    assert {f.name for f in desk} == set(emitted)
    # A bucket's momentum appears once the clock has passed the bucket's end.
    for number in range(1, 9):
        assert emitted[f"momentum(min-{number:02d})"] >= number * 300.0


@pytest.mark.parametrize(("story", "seed"), STORIES)
def test_no_label_or_aggregate_description_shows_raw_time(
    story: str, seed: int
) -> None:
    m = lean(story, seed)
    reg = m.registry
    anchor = (
        next(
            e
            for e in m.events
            if e.type.value == "card"
            and e.outcome is not None
            and e.outcome.value == "red"
        )
        if story == "red_card_flip"
        else m.events[len(m.events) // 2]
    )
    since(anchor.id.root, reg, m.events, [])
    last_minutes(11, reg, m.events)
    ctx = LabelContext(TEAMS, {e.id.root: e for e in m.events}, reg)
    labels = [label_for(f, ctx) for f in reg.all()]
    assert not [x for x in labels if RAW_TIME.search(x)]
    assert not [d for d in reg.aggregates.values() if RAW_TIME.search(d)]
    assert any("(to " in label_for(f, ctx) for f in reg.all() if ", last " in f.name)
