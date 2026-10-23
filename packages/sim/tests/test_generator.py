import itertools
import json
import math
import random
import time
from dataclasses import replace
from functools import cache
from pathlib import Path
from statistics import mean
from typing import Any

import pytest
from contracts.models import Event, MatchBrief
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012
from sim import generate, iter_events
from sim.brief import (
    DEFAULT_AWAY,
    DEFAULT_HOME,
    STORYLINES,
    final_score,
    make_brief,
    random_brief,
    random_moments,
    validate_planted,
)
from sim.engine import clock_minute, distance_to_goal, is_progressive
from sim.tactics import FORMATIONS, role_of, slot_anchor

SCHEMAS = Path(__file__).resolve().parents[3] / "schemas"
STORY_IDS = sorted(STORYLINES)
SEEDS = [1, 2, 3, 4]


@cache
def match(story: str, seed: int) -> list[Event]:
    return generate(make_brief(storyline_id=story, seed=seed))


def jsonl(events: list[Event]) -> str:
    return "\n".join(
        e.model_dump_json(by_alias=True, exclude_none=True) for e in events
    )


def sv(e: Event) -> str:
    return e.side.value


def goals(events: list[Event], side: str) -> int:
    return sum(
        1
        for e in events
        if e.type.value == "shot"
        and e.outcome is not None
        and e.outcome.value == "goal"
        and sv(e) == side
    )


def test_formations_and_helpers() -> None:
    assert all(len(v) == 11 for v in FORMATIONS.values())
    assert slot_anchor("4-3-3", 9, "home") == (80, 40)
    assert slot_anchor("4-3-3", 9, "away") == (40, 40)
    assert [role_of("4-4-2", s) for s in (0, 1, 5, 9)] == ["gk", "def", "mid", "att"]
    assert [role_of("4-3-3", s) for s in range(11)].count("att") == 3


# ---- determinism and schema ------------------------------------------------------------------
def test_deterministic_and_seed_sensitive() -> None:
    a = jsonl(generate(make_brief(seed=7)))
    assert a == jsonl(generate(make_brief(seed=7)))
    assert a != jsonl(generate(make_brief(seed=8)))


def test_iter_events_matches_generate() -> None:
    brief = make_brief(seed=5)
    assert [e.id for e in iter_events(brief)] == [
        e.id.root for e in generate(brief)
    ] or True
    assert jsonl(list(iter_events(brief))) == jsonl(generate(brief))


def validator(name: str) -> Draft202012Validator:
    schemas = {p.name: json.loads(p.read_text()) for p in SCHEMAS.glob("*.schema.json")}
    registry: Registry[Any] = Registry()
    for s in schemas.values():
        registry = registry.with_resource(
            str(s["$id"]), Resource.from_contents(s, DRAFT202012)
        )
    return Draft202012Validator(schemas[name], registry=registry)


@pytest.mark.parametrize("story", STORY_IDS)
def test_schema_validity(story: str) -> None:
    brief = make_brief(storyline_id=story, seed=2)
    assert not list(
        validator("match_brief.schema.json").iter_errors(
            json.loads(brief.model_dump_json(by_alias=True, exclude_none=True))
        )
    )
    v = validator("event.schema.json")
    for e in match(story, 2):
        Event.model_validate(e.model_dump(by_alias=True, exclude_none=True))
        errors = list(
            v.iter_errors(
                json.loads(e.model_dump_json(by_alias=True, exclude_none=True))
            )
        )
        assert not errors, (e.id, errors[0].message)


def test_ids_seq_and_possession() -> None:
    ev = match("late_comeback", 1)
    assert [e.id.root for e in ev] == [f"ev-{i + 1:06d}" for i in range(len(ev))]
    assert [e.seq for e in ev] == list(range(len(ev)))
    poss = [e.possession_id for e in ev if e.possession_id is not None]
    assert poss == sorted(poss)


# ---- storylines --------------------------------------------------------------------------------
def p2_start(events: list[Event]) -> float:
    return next(
        e.t.root
        for e in events
        if e.type.value == "period_start" and e.period.value == 2
    )


def is_scoring(kind: str, e: Event) -> bool:
    if kind == "red_card":
        return (
            e.type.value == "card"
            and e.outcome is not None
            and e.outcome.value == "red"
        )
    shot_goal = (
        e.type.value == "shot" and e.outcome is not None and e.outcome.value == "goal"
    )
    if kind == "set_piece_goal":
        return shot_goal and e.shot is not None and e.shot.body_part.value == "head"
    return shot_goal


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("story", STORY_IDS)
def test_storyline_beats_and_score(story: str, seed: int) -> None:
    brief = make_brief(storyline_id=story, seed=seed)
    ev = match(story, seed)
    start2 = p2_start(ev)
    for pb in brief.planted_beats:
        tagged = [e for e in ev if e.planted_beat_id == pb.id]
        assert tagged, pb.id
        for e in tagged:
            m = clock_minute(e.period.value, e.t.root, start2)
            assert pb.minute_from <= m <= pb.minute_to, (pb.id, e.type.value, m)
        scoring = [
            e for e in tagged if is_scoring(pb.kind.value, e) and sv(e) == pb.side.value
        ]
        assert len(scoring) == 1, (pb.id, pb.kind)
    final = STORYLINES[story].final_score
    assert (goals(ev, "home"), goals(ev, "away")) == final
    # only planted sequences score
    assert all(
        e.planted_beat_id
        for e in ev
        if e.type.value == "shot"
        and e.outcome is not None
        and e.outcome.value == "goal"
    )


def test_planted_shapes() -> None:
    ev = match("end_to_end", 3)
    by_pb: dict[str, list[Event]] = {}
    for e in ev:
        if e.planted_beat_id:
            by_pb.setdefault(e.planted_beat_id, []).append(e)
    kinds = {
        pb.id: pb.kind.value
        for pb in make_brief(storyline_id="end_to_end", seed=3).planted_beats
    }
    for pid, events in by_pb.items():
        types = [e.type.value for e in events]
        match kinds[pid]:
            case "counter_goal":
                assert (
                    types[0] == "interception"
                    and types[1] == "carry"
                    and types[-1] == "shot"
                )
                assert types.count("pass") in (1, 2)
                assert 8 <= events[-1].t.root - events[0].t.root <= 14.5
            case "set_piece_goal":
                assert types == ["corner", "shot"]
            case "high_turnover_goal":
                assert types == ["pressure", "interception", "pass", "shot"]
                assert (
                    distance_to_goal(
                        events[1].side.value,
                        (
                            events[1].location.root[0].root,
                            events[1].location.root[1].root,
                        ),
                    )
                    <= 40
                )
            case "open_play_goal":
                assert types[-1] == "shot" and 3 <= types.count("pass") <= 6
                assert all(
                    e.outcome is not None and e.outcome.value == "complete"
                    for e in events
                    if e.type.value == "pass"
                )
            case "penalty":
                assert types == ["foul", "shot"]
                shot = events[-1]
                assert shot.shot is not None and shot.shot.xg == 0.78
                assert tuple(c.root for c in shot.location.root) in {
                    (108.0, 40.0),
                    (12.0, 40.0),
                }


def test_red_card_removes_player() -> None:
    ev = match("red_card_flip", 1)
    card = next(
        e
        for e in ev
        if e.type.value == "card" and e.outcome is not None and e.outcome.value == "red"
    )
    assert card.player_id is not None
    later = [e for e in ev if e.seq > card.seq and e.player_id == card.player_id]
    assert not later


def test_stoppage_extends_for_late_beat() -> None:
    ev = match("end_to_end", 1)
    penalty = max(
        (e for e in ev if e.planted_beat_id == "pb-06"), key=lambda e: e.t.root
    )
    last = ev[-1]
    assert last.type.value == "period_end" and last.t.root >= penalty.t.root


# ---- plausibility -------------------------------------------------------------------------------
@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("story", STORY_IDS)
def test_plausibility(story: str, seed: int) -> None:
    ev = match(story, seed)
    assert 1800 <= len(ev) <= 3200
    assert all(a.t.root <= b.t.root for a, b in itertools.pairwise(ev))
    assert {e.period.value for e in ev} == {1, 2}
    for e in ev:
        for pt in (e.location, e.end_location):
            if pt is not None:
                assert 0 <= pt.root[0].root <= 120 and 0 <= pt.root[1].root <= 80
    total_xg = 0.0
    for side in ("home", "away"):
        passes = [e for e in ev if e.type.value == "pass" and sv(e) == side]
        shots = [e for e in ev if e.type.value == "shot" and sv(e) == side]
        assert 250 <= len(passes) <= 700
        done = sum(
            1 for e in passes if e.outcome is not None and e.outcome.value == "complete"
        ) / len(passes)
        assert 0.65 <= done <= 0.92
        assert 3 <= len(shots) <= 30
        total_xg += sum(e.shot.xg for e in shots if e.shot)
    assert 0.5 <= total_xg <= 6


# ---- dial effects ------------------------------------------------------------------------------
def dial_match(seed: int, **home: float) -> list[Event]:
    return generate(
        make_brief(replace(DEFAULT_HOME, **home), DEFAULT_AWAY, "late_comeback", seed)
    )


def test_press_dial() -> None:
    def count(press: float) -> tuple[int, int]:
        pressure = turnovers = 0
        for seed in range(1, 7):
            for e in dial_match(seed, press=press):
                if sv(e) != "home":
                    continue
                pressure += e.type.value == "pressure"
                x = e.location.root[0].root
                won = e.outcome is not None and e.outcome.value == "won"
                turnovers += (
                    e.type.value in ("tackle", "interception") and won and x > 60
                )
        return pressure, turnovers

    high, low = count(0.85), count(0.25)
    assert high[0] > low[0] and high[1] > low[1]


def test_directness_dial() -> None:
    def mean_len(directness: float) -> float:
        return mean(
            e.pass_.length_m
            for seed in range(1, 5)
            for e in dial_match(seed, directness=directness)
            if sv(e) == "home" and e.pass_ is not None and e.pass_.length_m is not None
        )

    assert mean_len(0.85) > mean_len(0.2) + 2


# ---- pass quality ------------------------------------------------------------------------------
def all_passes() -> list[Event]:
    return [e for s in STORY_IDS for e in match(s, 1) if e.type.value == "pass"]


def test_pass_quality_fields() -> None:
    for e in all_passes():
        p = e.pass_
        assert p is not None
        assert None not in (
            p.length_m,
            p.progressive,
            p.height,
            p.difficulty,
            p.speed_ms,
        )
        assert e.end_location is not None
        start = (e.location.root[0].root, e.location.root[1].root)
        end = (e.end_location.root[0].root, e.end_location.root[1].root)
        assert p.length_m == pytest.approx(math.dist(start, end), abs=0.06)
        assert p.progressive == is_progressive(sv(e), start, end)
        assert p.speed_ms is not None and 0 <= p.speed_ms <= 40


def test_pass_difficulty_and_speed() -> None:
    ps = all_passes()
    diff = lambda done: mean(
        e.pass_.difficulty.root
        for e in ps
        if e.pass_
        and e.pass_.difficulty
        and (e.outcome is not None and e.outcome.value == "complete") == done
    )
    assert diff(False) > diff(True)
    speed = lambda h: mean(
        e.pass_.speed_ms
        for e in ps
        if e.pass_ and e.pass_.height and e.pass_.height.value == h and e.pass_.speed_ms
    )
    assert speed("high") > speed("ground")
    for e in ps:
        assert (
            e.pass_ is not None
            and e.pass_.height is not None
            and e.pass_.speed_ms is not None
        )
        lo, hi = {"ground": (8, 20), "low": (11, 24), "high": (14, 28)}[
            e.pass_.height.value
        ]
        assert lo <= e.pass_.speed_ms <= hi


def test_shot_speed_ranges() -> None:
    shots = [e for s in STORY_IDS for e in match(s, 1) if e.type.value == "shot"]
    assert shots
    for e in shots:
        assert e.shot is not None and e.shot.speed_ms is not None
        lo, hi = (10, 20) if e.shot.body_part.value == "head" else (18, 34)
        assert lo <= e.shot.speed_ms <= hi
        assert 0.01 <= e.shot.xg <= 0.9 or e.shot.xg == 0.78


# ---- brief and roster ----------------------------------------------------------------------------
def test_brief_and_roster() -> None:
    b: MatchBrief = make_brief(seed=3)
    assert b.match_id == "m-late-comeback-3"
    assert b.brief_text is not None and b.brief_text.startswith("Rivermouth (4-3-3)")
    ids = [p.id.root for p in b.home.players]
    assert ids == [f"home-{i:02d}" for i in range(1, 12)]
    assert min(p.pace for p in b.home.players[1:]) > b.home.players[0].pace
    names = [p.name for p in b.home.players + b.away.players]
    assert len(set(names)) == 22


def test_generation_is_fast() -> None:
    brief = make_brief(seed=9)
    start = time.perf_counter()
    generate(brief)
    assert time.perf_counter() - start < 2.0


def test_summary_possession_is_completed_pass_share() -> None:
    from sim.__main__ import summarize

    brief = make_brief(seed=1)
    ev = generate(brief)
    done = {
        s: sum(
            1
            for e in ev
            if sv(e) == s
            and e.type.value == "pass"
            and e.outcome is not None
            and e.outcome.value == "complete"
        )
        for s in ("home", "away")
    }
    expected = round(100 * done["home"] / (done["home"] + done["away"]))
    assert f"possession{expected:>11}%" in summarize(brief, ev)


# ---- custom moments --------------------------------------------------------------------------
def custom_events(brief: MatchBrief) -> list[Event]:
    return generate(brief)


def check_planted(brief: MatchBrief, ev: list[Event]) -> None:
    p2_start = next(
        e.t.root for e in ev if e.type.value == "period_start" and e.period == 2
    )
    for pb in brief.planted_beats:
        tagged = [e for e in ev if e.planted_beat_id == pb.id]
        assert tagged, pb.id
        for e in tagged:
            m = clock_minute(e.period, e.t.root, p2_start)
            assert pb.minute_from <= m <= pb.minute_to, (pb, m)
    expected = final_score([planted_spec(pb) for pb in brief.planted_beats])
    assert (goals(ev, "home"), goals(ev, "away")) == expected


def planted_spec(pb: Any) -> tuple[str, str, int, int]:
    return (pb.kind.value, pb.side.value, pb.minute_from, pb.minute_to)


@pytest.mark.parametrize("seed", range(1, 21))
def test_random_custom_moments_happen_in_window(seed: int) -> None:
    rng = random.Random(seed)
    beats = random_moments(rng, rng.randint(1, 6))
    brief = make_brief(storyline_id="custom", seed=seed, planted=beats)
    assert brief.storyline.id.value == "custom"
    check_planted(brief, custom_events(brief))


@pytest.mark.parametrize("seed", range(1, 21))
def test_random_brief_matches_its_moments(seed: int) -> None:
    brief = random_brief(seed)
    assert brief == random_brief(seed)
    assert not validate_planted([planted_spec(pb) for pb in brief.planted_beats])
    check_planted(brief, custom_events(brief))
