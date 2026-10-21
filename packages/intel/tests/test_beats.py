import json
import re
from functools import cache
from pathlib import Path
from typing import Any

import pytest
from contracts.models import Beat
from intel.beats import (
    BIG_CHANCE_XG,
    DEBOUNCE_S,
    GOAL_KINDS,
    BeatDetector,
    beat_id,
    detect_all,
    minute_text,
)
from intel.engine import FactEngine, extract_all
from intel.registry import FactRegistry
from jsonschema import Draft202012Validator
from matches import match
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012
from sim.brief import DEFAULT_AWAY, DEFAULT_HOME, make_brief

ROOT = Path(__file__).resolve().parents[3]
STORIES = ("late_comeback", "red_card_flip", "smash_and_grab", "end_to_end")
SEEDS = (1, 2, 3, 4)
# The beat kinds a planted beat may be detected as. A high-turnover goal is a high_turnover_chance
# anchored on the goal; a penalty has no restart event of its own, so it reads as an open-play goal.
EXPECTED_KINDS = {
    "counter_goal": {"counter_goal"},
    "set_piece_goal": {"set_piece_goal"},
    "open_play_goal": {"open_play_goal"},
    "high_turnover_goal": {"high_turnover_chance"},
    "red_card": {"card"},
    "penalty": {"open_play_goal"},
}


@cache
def detected(story: str, seed: int) -> tuple[list[Beat], FactRegistry]:
    m = match(story, seed)
    registry = extract_all(m.events, m.frames, m.freeze)
    return detect_all(m.events, m.frames, m.freeze, registry), registry


def beat_validator() -> Draft202012Validator:
    schemas = {
        p.name: json.loads(p.read_text())
        for p in (ROOT / "schemas").glob("*.schema.json")
    }
    registry: Registry[Any] = Registry()
    for s in schemas.values():
        registry = registry.with_resource(
            str(s["$id"]), Resource.from_contents(s, DRAFT202012)
        )
    return Draft202012Validator(schemas["beat.schema.json"], registry=registry)


def dump(b: Beat) -> dict[str, Any]:
    out: dict[str, Any] = json.loads(
        b.model_dump_json(by_alias=True, exclude_none=True)
    )
    return out


@pytest.mark.parametrize("story", STORIES)
def test_beats_validate_and_every_fact_exists(story: str) -> None:
    beats, registry = detected(story, 1)
    check = beat_validator()
    ids = [b.id.root for b in beats]
    assert len(ids) == len(set(ids))
    for b in beats:
        check.validate(dump(b))
        assert b.id.root == beat_id(b.anchor_event_id.root, b.kind.value)
        assert b.fact_ids
        for fid in b.fact_ids:
            registry.get(fid.root)


@pytest.mark.parametrize(("story", "seed"), [(s, n) for s in STORIES for n in SEEDS])
def test_planted_beats_are_detected_as_planted(story: str, seed: int) -> None:
    beats, _ = detected(story, seed)
    brief = make_brief(DEFAULT_HOME, DEFAULT_AWAY, story, seed)
    for planted in brief.planted_beats:
        pid = planted.id
        kinds = EXPECTED_KINDS[planted.kind.value]
        found = [b for b in beats if b.planted_beat_id == pid and b.kind.value in kinds]
        assert found, (
            f"{story}/{seed}: {pid} {planted.kind.value} not detected as {kinds}"
        )
        assert all(b.origin.value == "planted" for b in found)
    for b in beats:
        assert (b.origin.value == "planted") == (b.planted_beat_id is not None)


@pytest.mark.parametrize("seed", SEEDS)
def test_red_card_has_a_momentum_swing_follow_up(seed: int) -> None:
    m = match("red_card_flip", seed)
    beats, registry = detected("red_card_flip", seed)
    cards = [
        e
        for e in m.events
        if e.type.value == "card" and e.outcome and e.outcome.value == "red"
    ]
    assert len(cards) == 1
    card = cards[0]
    swing = [
        b
        for b in beats
        if b.kind.value == "momentum_swing" and b.anchor_event_id.root == card.id.root
    ]
    assert len(swing) == 1
    facts = [registry.get(f.root) for f in swing[0].fact_ids]
    changes = [
        f
        for f in facts
        if f.name.startswith("back_line_change(")
        and f.scope is not None
        and f.scope.side is not None
        and f.scope.side.value == card.side.value
    ]
    assert changes
    assert float(changes[0].value) >= 4.0


@pytest.mark.parametrize(
    ("story", "seed"), [("red_card_flip", 3), ("late_comeback", 1)]
)
def test_live_equals_batch(story: str, seed: int) -> None:
    m = match(story, seed)
    engine = FactEngine()
    detector = BeatDetector()
    live: list[Beat] = []
    for item in m.stream:
        engine.push(item)
        live += detector.push(item, engine.registry)
    engine.finish()
    live += detector.finish(engine.registry)
    batch, _ = detected(story, seed)
    assert [dump(b) for b in live] == [dump(b) for b in batch]


def test_detection_is_deterministic() -> None:
    m = match("end_to_end", 2)
    runs = [
        detect_all(
            m.events, m.frames, m.freeze, extract_all(m.events, m.frames, m.freeze)
        )
        for _ in range(2)
    ]
    assert [dump(b) for b in runs[0]] == [dump(b) for b in runs[1]]


@pytest.mark.parametrize("story", STORIES)
def test_rules_hold(story: str) -> None:
    m = match(story, 1)
    beats, _ = detected(story, 1)
    by_id = {e.id.root: e for e in m.events}
    last: dict[tuple[str, str], float] = {}
    for b in sorted(beats, key=lambda x: (x.t_to.root, x.id.root)):
        kind, side = b.kind.value, b.side.value if b.side else ""
        anchor = by_id[b.anchor_event_id.root]
        assert 0.0 <= b.salience <= 1.0
        assert b.t_from.root <= b.t_to.root <= b.t_detect.root
        if kind not in GOAL_KINDS and kind not in (
            "territorial_spell",
            "momentum_swing",
        ):
            if (kind, side) in last:
                assert b.t_to.root - last[(kind, side)] >= DEBOUNCE_S
            last[(kind, side)] = b.t_to.root
        if kind == "big_chance":
            assert anchor.shot is not None and anchor.shot.xg >= BIG_CHANCE_XG
            assert anchor.outcome is not None and anchor.outcome.value != "goal"
        if kind in GOAL_KINDS:
            assert anchor.outcome is not None and anchor.outcome.value == "goal"
        if kind == "card":
            assert anchor.outcome is not None and anchor.outcome.value == "red"
    salience = {
        k: max((b.salience for b in beats if b.kind.value == k), default=0.0)
        for k in ("territorial_spell", "big_chance", "momentum_swing", "card")
    }
    goals = [b.salience for b in beats if b.kind.value in GOAL_KINDS]
    if goals:
        assert (
            min(goals) >= salience["card"] >= salience["momentum_swing"]
            or salience["card"] == 0
        )
    assert salience["territorial_spell"] <= 0.30


def test_label_forms() -> None:
    assert minute_text(40 * 60 + 12, 1) == "41"
    assert minute_text(46 * 60 + 5, 1) == "45+2"
    assert minute_text(92 * 60 + 30, 2) == "90+3"
    assert re.fullmatch(r"\d+′|\d+(\+\d+)?–\d+(\+\d+)?′|\d+\+\d+′", "55–70′")


@pytest.mark.parametrize("story", STORIES)
def test_label_shapes(story: str) -> None:
    beats, _ = detected(story, 1)
    shape = re.compile(r"^\d+(\+\d+)?(–\d+(\+\d+)?)?′$")
    assert all(shape.match(b.label) for b in beats)


def test_beats_per_match_report(capsys: pytest.CaptureFixture[str]) -> None:
    with capsys.disabled():
        for story in STORIES:
            counts = [len(detected(story, seed)[0]) for seed in SEEDS]
            print(f"\nbeats {story}: {counts} (target 12-30, not asserted)", end="")
