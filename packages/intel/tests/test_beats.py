import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from beat_checks import (
    SEEDS,
    STORIES,
    check_planted,
)
from contracts.models import Beat
from intel.__main__ import main as intel_main
from intel.beats import (
    BIG_CHANCE_XG,
    DEBOUNCE_S,
    GOAL_KINDS,
    MIN_SINCE_S,
    BeatDetector,
    beat_id,
    detect_all,
    minute_text,
)
from intel.engine import FactEngine, extract_all
from jsonschema import Draft202012Validator
from matches import Lean, compute_lean, gc_paused, lean, match
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012
from sim.__main__ import main as sim_main
from sim.brief import DEFAULT_AWAY, DEFAULT_HOME, make_brief

ROOT = Path(__file__).resolve().parents[3]


def batch_beats(story: str, seed: int) -> list[Beat]:
    """The same beats from the finished match, through detect_all."""
    m = match(story, seed)
    with gc_paused():
        registry = extract_all(m.events, m.frames, m.freeze)
        return detect_all(m.events, m.frames, m.freeze, registry)


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


def check_valid_and_facts_exist(found: Lean) -> None:
    beats, registry = found.beats, found.registry
    check = beat_validator()
    ids = [b.id.root for b in beats]
    assert len(ids) == len(set(ids))
    for b in beats:
        check.validate(dump(b))
        assert b.id.root == beat_id(b.anchor_event_id.root, b.kind.value)
        assert b.fact_ids
        for fid in b.fact_ids:
            registry.get(fid.root)


def check_one_beat_per_anchor(found: Lean) -> None:
    beats = found.beats
    anchored = [
        b.anchor_event_id.root for b in beats if b.kind.value != "momentum_swing"
    ]
    assert len(anchored) == len(set(anchored))
    follow_ups = [b for b in beats if b.kind.value == "momentum_swing"]
    by_anchor = {
        b.anchor_event_id.root: b for b in beats if b.kind.value != "momentum_swing"
    }
    assert all(b.anchor_event_id.root in by_anchor for b in follow_ups)


def check_high_turnover_goal_is_one_planted_beat(
    story: str, seed: int, found: Lean
) -> None:
    beats = found.beats
    brief = make_brief(DEFAULT_HOME, DEFAULT_AWAY, story, seed)
    for planted in brief.planted_beats:
        if planted.kind.value != "high_turnover_goal":
            continue
        own = [b for b in beats if b.planted_beat_id == planted.id]
        assert [b.kind.value for b in own] == ["high_turnover_goal"]
        assert own[0].origin.value == "planted"


def check_stoppage_time_goal_has_no_follow_up(found: Lean) -> None:
    beats, events = found.beats, found.events
    late = [
        e
        for e in events
        if e.type.value == "shot"
        and e.outcome is not None
        and e.outcome.value == "goal"
        and e.t.root > events[-1].t.root - MIN_SINCE_S
    ]
    assert late  # the 90+7 goal
    anchors = {
        b.anchor_event_id.root for b in beats if b.kind.value == "momentum_swing"
    }
    assert not anchors & {e.id.root for e in late}
    assert any(
        b.anchor_event_id.root == late[0].id.root for b in beats
    )  # the goal itself stays


def check_red_card_follow_up(found: Lean) -> None:
    beats, registry = found.beats, found.registry
    cards = [
        e
        for e in found.events
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
    ("story", "seed"),
    [("red_card_flip", 3), pytest.param("late_comeback", 1, marks=pytest.mark.slow)],
)
def test_live_equals_batch(story: str, seed: int) -> None:
    m = match(story, seed)
    engine = FactEngine()
    detector = BeatDetector()
    live: list[Beat] = []
    with gc_paused():
        for item in m.stream:
            engine.push(item)
            live += detector.push(item, engine.registry)
        engine.finish()
        live += detector.finish(engine.registry)
    assert [dump(b) for b in live] == [dump(b) for b in batch_beats(story, seed)]


@pytest.mark.slow
def test_detection_is_deterministic() -> None:
    runs = [compute_lean("end_to_end", 2).beats for _ in range(2)]
    assert [dump(b) for b in runs[0]] == [dump(b) for b in runs[1]]


def check_rules_hold(found: Lean) -> None:
    beats = found.beats
    by_id = {e.id.root: e for e in found.events}
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


def check_label_shapes(found: Lean) -> None:
    shape = re.compile(r"^\d+(\+\d+)?(–\d+(\+\d+)?)?′$")
    assert all(shape.match(b.label) for b in found.beats)


# The fast suite checks one seed per storyline; the other seeds run with `make slow`.
MATCHES = [
    pytest.param(s, n, marks=[pytest.mark.slow] if n != SEEDS[0] else [])
    for s in STORIES
    for n in SEEDS
]


@pytest.mark.parametrize(("story", "seed"), MATCHES)
def test_beats_of_a_match(story: str, seed: int) -> None:
    """Every check that needs only a match's beats, so each of the 16 matches is built once."""
    found = lean(story, seed)
    check_planted(story, seed, found.beats)
    if story in ("late_comeback", "end_to_end"):
        check_high_turnover_goal_is_one_planted_beat(story, seed, found)
    if story == "red_card_flip":
        check_red_card_follow_up(found)
    if seed == 1:
        check_valid_and_facts_exist(found)
        check_one_beat_per_anchor(found)
        check_rules_hold(found)
        check_label_shapes(found)
        if story == "end_to_end":
            check_stoppage_time_goal_has_no_follow_up(found)


PEAK_RSS_LIMIT_MB = 1024  # the 16 matches one after another must fit in this


@pytest.mark.slow
def test_planted_matrix_stays_under_the_memory_limit(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """All 16 matches in a fresh process, so the peak is theirs and not the rest of the suite's."""
    code = (
        "import json; from beat_checks import peak_rss_mb, run_planted_matrix; "
        "counts = run_planted_matrix(); "
        "print(json.dumps([[k[0], k[1], v] for k, v in counts.items()])); "
        "print(peak_rss_mb())"
    )
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).parent)}
    done = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    counts_line, raw = done.stdout.strip().splitlines()[-2:]
    peak_mb = float(raw)
    per_story = {
        story: [n for s, _, n in json.loads(counts_line) if s == story]
        for story in STORIES
    }
    with capsys.disabled():
        print(f"\nbeats per match (target 12-30, not asserted): {per_story}")
        print(f"peak RSS of the 16-match check: {peak_mb:.0f} MB", end="")
    assert peak_mb < PEAK_RSS_LIMIT_MB


@pytest.mark.parametrize(("story", "seed"), [("late_comeback", 4), ("end_to_end", 1)])
def test_beats_command_writes_every_fact_it_cites(
    story: str, seed: int, tmp_path: Path
) -> None:
    out = tmp_path / f"m-{story.replace('_', '-')}-{seed}.jsonl"
    assert (
        sim_main(["generate", "--story", story, "--seed", str(seed), "--out", str(out)])
        == 0
    )
    base = tmp_path / out.stem
    assert intel_main(["beats", "--match", str(base)]) == 0
    beats = [
        json.loads(x)
        for x in (tmp_path / f"{out.stem}.beats.jsonl").read_text().splitlines()
    ]
    facts = {
        json.loads(x)["id"]
        for x in (tmp_path / f"{out.stem}.facts.jsonl").read_text().splitlines()
    }
    cited = {fid for b in beats for fid in b["fact_ids"]}
    assert beats
    assert cited <= facts
    assert any(
        "-since-" in fid or "-before-" in fid for fid in cited
    )  # on-demand facts are in
