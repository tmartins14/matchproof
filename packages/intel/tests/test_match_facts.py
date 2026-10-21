import json
import time
from pathlib import Path
from typing import Any

import pytest
import yaml
from contracts.models import Event
from intel import (
    extract_events,
    extract_positions,
)
from intel import (
    since as since_module,
)
from intel.engine import FactEngine, extract_all
from intel.registry import FactRegistry
from intel.since import last_minutes, since
from intel.windows import windows
from jsonschema import Draft202012Validator
from matches import match
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012
from sim.positions import freeze_source_id

ROOT = Path(__file__).resolve().parents[3]
STORIES = [("red_card_flip", 3), ("late_comeback", 1)]
EXAMPLES = yaml.safe_load((ROOT / "voice/examples.yaml").read_text())


def batch(story: str, seed: int) -> FactRegistry:
    m = match(story, seed)
    return extract_all(m.events, m.frames, m.freeze)


def lines(reg: FactRegistry) -> list[str]:
    return [f.model_dump_json(by_alias=True, exclude_none=True) for f in reg.all()]


def validator() -> Draft202012Validator:
    schemas = {
        p.name: json.loads(p.read_text())
        for p in (ROOT / "schemas").glob("*.schema.json")
    }
    registry: Registry[Any] = Registry()
    for s in schemas.values():
        registry = registry.with_resource(
            str(s["$id"]), Resource.from_contents(s, DRAFT202012)
        )
    return Draft202012Validator(schemas["fact.schema.json"], registry=registry)


@pytest.mark.parametrize(("story", "seed"), STORIES)
def test_facts_validate_and_every_source_exists(story: str, seed: int) -> None:
    m = match(story, seed)
    reg = batch(story, seed)
    check = validator()
    known = {e.id.root for e in m.events}
    known |= {freeze_source_id(e.id.root) for e in m.events}
    known |= {w.id for w in windows(m.events)}
    known |= set(reg.aggregates)
    assert len(reg) > 1000
    for fact in reg.all():
        check.validate(
            json.loads(fact.model_dump_json(by_alias=True, exclude_none=True))
        )
        assert fact.source_ids, fact.name
        missing = [s.root for s in fact.source_ids if s.root not in known]
        assert not missing, (fact.name, missing)


def test_same_match_gives_byte_identical_facts() -> None:
    first = lines(batch("red_card_flip", 3))
    # A fresh extraction from freshly loaded models, not a cached object.
    m = match("red_card_flip", 3)
    again = lines(
        extract_all(
            [Event.model_validate(e.model_dump(by_alias=True)) for e in m.events],
            m.frames,
            m.freeze,
        )
    )
    assert "\n".join(first).encode() == "\n".join(again).encode()


@pytest.mark.parametrize(("story", "seed"), STORIES)
def test_batch_equals_incremental_at_full_time(story: str, seed: int) -> None:
    m = match(story, seed)
    engine = FactEngine()
    emitted = 0
    for item in m.stream:
        emitted += len(engine.push(item))
    assert emitted == len(engine.registry)
    assert engine.finish() == []
    assert engine.registry == batch(story, seed)
    assert lines(engine.registry) == lines(batch(story, seed))


def test_window_facts_arrive_when_the_window_closes() -> None:
    m = match("red_card_flip", 3)
    engine = FactEngine()
    seen: dict[str, float] = {}
    for item in m.stream:
        for fact in engine.push(item):
            if fact.name.endswith("win-01)") or ", win-01, " in fact.name:
                seen.setdefault(fact.id.root, item.t.root)
    assert seen
    assert (
        min(seen.values()) >= 900.0
    )  # nothing for win-01 until the clock passes 15:00


def test_speed_whole_match_with_frames() -> None:
    m = match("red_card_flip", 3)
    start = time.perf_counter()
    extract_all(m.events, m.frames, m.freeze)
    assert time.perf_counter() - start < 6.0


# ---- since() -------------------------------------------------------------------------------------
def red_card(m_events: list[Event]) -> Event:
    return next(
        e
        for e in m_events
        if e.type.value == "card" and e.outcome is not None and e.outcome.value == "red"
    )


def test_since_gives_before_after_and_change_for_the_red_card() -> None:
    m = match("red_card_flip", 3)
    reg = batch("red_card_flip", 3)
    anchor = red_card(m.events)
    aid = anchor.id.root
    made = since(aid, reg, m.events, m.frames)
    names = {f.name: f for f in made}
    now = f"{max(e.t.root for e in m.events):.2f}"
    side = anchor.side.value
    before = names[f"back_line_height({side}, before {aid})"]
    after = names[f"back_line_height({side}, since {aid} to t{now})"]
    change = names[f"back_line_change({side}, {aid}, to t{now})"]
    assert change.value == abs(round(float(before.value)) - round(float(after.value)))
    assert aid in {s.root for s in change.source_ids}
    assert {s.root for s in change.source_ids} == {
        s.root for s in (*before.source_ids, *after.source_ids)
    }
    assert all(reg.has_name(f.name) for f in made)
    assert (
        since(aid, reg, m.events, m.frames) == made
    )  # asking again is the same, not a conflict


def test_since_registered_aggregates_exist() -> None:
    m = match("red_card_flip", 3)
    reg = batch("red_card_flip", 3)
    for f in since(red_card(m.events).id.root, reg, m.events, m.frames):
        assert all(
            s.root.startswith(("ev-", "win-")) or s.root in reg.aggregates
            for s in f.source_ids
        )


# ---- coverage of voice/examples.yaml ---------------------------------------------------------------
# Example fact id -> the metric that produces it. KNOWN_GAPS would hold facts the event schema cannot support.
COVERAGE: dict[str, str] = {
    "fx-0101": "freeze_frame.home_ahead_of_ball",  # the side caught high has N players ahead of the ball
    "fx-0102": "freeze_frame.attackers_v_defenders",
    "fx-0103": "sequence.seconds",
    "fx-0201": "since.territory",  # last 10 minutes
    "fx-0202": "since.shots",
    "fx-0301": "since.possession_share",
    "fx-0401": "freeze_frame.defenders_drawn",
    "fx-0402": "shot.xg",
    "fx-0501": "card.kind",
    "fx-0502": "card.players_after",
    "fx-0601": "since.possession_share",
    "fx-0602": "since.touches_in_opponent_half",
    "fx-0701": "corners",
    "fx-0702": "freeze_frame.shooter_nearest_defender",
    "fx-0801": "sequence.ball_won_distance",
    "fx-0901": "since.back_line_height",
    "fx-0902": "since.back_line_height",
    "fx-0903": "since.back_line_change",
    "fx-1001": "since.compactness",
    "fx-1002": "since.compactness",
    "fx-1003": "since.line_breaking_passes",
    "fx-1101": "since.press_rate",
    "fx-1102": "since.press_rate",
    "fx-1103": "since.high_turnovers",
    "fx-1201": "sequence.start_clock",
    "fx-1202": "sequence.shot_clock",
    "fx-1301": "since.back_line_change",
    "fx-1401": "since.possession_share",
    "fx-1501": "shot.shooter",
    "fx-1502": "shot.outcome",
}
KNOWN_GAPS: dict[str, str] = {}
CATALOGUE = {
    *extract_events.METRICS,
    *extract_events.SEQUENCE_METRICS,
    *extract_events.SHOT_METRICS,
    *extract_events.CARD_METRICS,
    *extract_positions.FREEZE_METRICS,
    *(f"since.{m}" for m in since_module.METRICS),
}


def example_fact_ids() -> set[str]:
    return {f["id"] for ex in EXAMPLES if ex["id"] != "ex-00" for f in ex["facts"]}


def test_every_example_fact_has_an_extractor() -> None:
    ids = example_fact_ids()
    assert ids == set(COVERAGE) | set(KNOWN_GAPS), (
        "examples and the coverage table are out of step"
    )
    unknown = {k: v for k, v in COVERAGE.items() if v not in CATALOGUE}
    assert not unknown, unknown
    print("\nexample fact -> extractor metric")
    for fid in sorted(ids):
        covered = COVERAGE.get(fid)
        print(f"  {fid}  {covered or 'NO EXTRACTOR: ' + KNOWN_GAPS[fid]}")


def test_every_covered_metric_is_actually_produced() -> None:
    """Run the extractors on a match and check each mapped metric turns up in the registry."""
    m = match("red_card_flip", 3)
    reg = batch("red_card_flip", 3)
    since(red_card(m.events).id.root, reg, m.events, m.frames)
    last_minutes(10, reg, m.events)
    produced: set[str] = set()
    for f in reg.all():
        head = f.name.split("(")[0]
        if f.name.startswith("freeze_frame("):
            produced.add("freeze_frame." + f.name.split(").", 1)[1])
        elif head in ("sequence", "shot", "card"):
            produced.add(f"{head}." + f.name.split(").", 1)[1])
        elif (
            "since " in f.name
            or "before " in f.name
            or "last " in f.name
            or ", to t" in f.name
        ):
            produced.add("since." + head)
        else:
            produced.add(head)
    missing = {
        fid: metric for fid, metric in COVERAGE.items() if metric not in produced
    }
    assert not missing, missing


# ---- one definition per measure --------------------------------------------------------------------
def test_match_level_shape_facts_equal_calibration() -> None:
    from sim.calibrate import shape_metrics
    from sim.geometry import aggregate

    m = match("red_card_flip", 3)
    reg = batch("red_card_flip", 3)
    cal = shape_metrics(m.frames)
    for i, side in enumerate(("home", "away")):
        for metric, key in (
            ("compactness", "compactness_out"),
            ("back_line_height", "back_line_height_out"),
        ):
            fact = reg.by_name(f"{metric}({side}, match, out_of_possession)")
            assert abs(float(fact.value) - cal[key][i]) < 1e-3, (side, metric)
    assert aggregate([1.0, 2.0, 10.0]) == 2.0  # the median, not the mean


# ---- shooter ---------------------------------------------------------------------------------------
def test_shooter_is_the_roster_name_or_the_player_id() -> None:
    m = match("red_card_flip", 3)
    shot = next(e for e in m.events if e.type.value == "shot" and e.player_id)
    pid = shot.player_id.root  # type: ignore[union-attr]
    name = f"shot({shot.id.root}).shooter"
    plain = batch("red_card_flip", 3).by_name(name)
    assert plain.value == pid and [s.root for s in plain.source_ids] == [shot.id.root]
    named = extract_all(m.events, m.frames, m.freeze, {pid: "Varga"})
    assert named.by_name(name).value == "Varga"
    engine = FactEngine({pid: "Varga"})
    for item in m.stream:
        engine.push(item)
    assert engine.registry == named
