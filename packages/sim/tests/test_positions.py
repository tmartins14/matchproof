import bisect
import itertools
import json
import math
import re
import time
from array import array
from collections.abc import Iterator
from dataclasses import replace
from functools import cache
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Any

import pytest
from contracts.models import Event, PositionFrame
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012
from sim import generate, iter_events
from sim.brief import DEFAULT_AWAY, DEFAULT_HOME, make_brief
from sim.geometry import back_line_height, hull_area
from sim.positions import (
    FRAME_DT,
    MAX_SPEED_V1,
    FrameSimulator,
    freeze_source_id,
    iter_frames,
    iter_freeze_frames,
    iter_stream,
    run,
)

ROOT = Path(__file__).resolve().parents[3]
JUMP_BOUND = MAX_SPEED_V1 * FRAME_DT + 0.05

# t, possession side, ball, player ids, then x, y, speed per player. Frames are kept as arrays:
# a million model objects make the garbage collector crawl.
Lite = tuple[float, str, tuple[float, float], tuple[str, ...], "array[float]"]
IDS: dict[tuple[str, ...], tuple[str, ...]] = {}


def lite(f: PositionFrame) -> Lite:
    ids = tuple(p.id.root for p in f.players)
    values: array[float] = array("d")
    for p in f.players:
        values.extend((p.at.root[0].root, p.at.root[1].root, p.speed_ms or 0.0))
    return (
        f.t.root,
        f.possession.value if f.possession is not None else "",
        (f.ball.root[0].root, f.ball.root[1].root),
        IDS.setdefault(ids, ids),
        values,
    )


def rows(f: Lite) -> Iterator[tuple[str, str, float, float, float]]:
    """(player id, side, x, y, speed) for each player in a lite frame."""
    for i, pid in enumerate(f[3]):
        yield pid, pid.split("-")[0], f[4][3 * i], f[4][3 * i + 1], f[4][3 * i + 2]


class Match:
    def __init__(self, story: str, seed: int, home_line: float | None = None) -> None:
        home = (
            DEFAULT_HOME
            if home_line is None
            else replace(DEFAULT_HOME, line_height=home_line)
        )
        self.brief = make_brief(home, DEFAULT_AWAY, story, seed)
        self.events: list[Event] = generate(self.brief)
        self.sim = FrameSimulator(self.brief)
        self.frames: list[Lite] = []
        self.sample: list[PositionFrame] = []
        self.freezes: dict[str, PositionFrame] = {}
        for kind, event, frame in run(self.brief, self.events, self.sim):
            if frame is None:
                continue
            if kind == "freeze" and event is not None:
                self.freezes[event.id.root] = frame
            elif kind == "frame":
                if len(self.frames) % 50 == 0:
                    self.sample.append(frame)
                self.frames.append(lite(frame))


@cache
def match(
    story: str = "late_comeback", seed: int = 1, home_line: float | None = None
) -> Match:
    return Match(story, seed, home_line)


def xy(p: Any) -> tuple[float, float]:
    return p.at.root[0].root, p.at.root[1].root


def test_frames_validate_against_schema() -> None:
    schemas = {
        p.name: json.loads(p.read_text())
        for p in (ROOT / "schemas").glob("*.schema.json")
    }
    registry: Registry[Any] = Registry()
    for s in schemas.values():
        registry = registry.with_resource(
            str(s["$id"]), Resource.from_contents(s, DRAFT202012)
        )
    validator = Draft202012Validator(
        schemas["position_frame.schema.json"], registry=registry
    )
    m = match()
    for f in m.sample + list(m.freezes.values()):
        errors = list(
            validator.iter_errors(
                json.loads(f.model_dump_json(by_alias=True, exclude_none=True))
            )
        )
        assert not errors, errors[0].message


def test_frame_output_is_deterministic() -> None:
    brief = make_brief(seed=3)
    events = generate(brief)

    def dump() -> str:
        return "\n".join(
            f.model_dump_json(exclude_none=True) for f in iter_frames(brief, events)
        )

    assert dump() == dump()


def test_pinning_actor_is_at_event_location_in_freeze_frame() -> None:
    m = match()
    checked = 0
    for e in m.events:
        if e.player_id is None:
            continue
        frame = m.freezes[e.id.root]
        assert (
            frame.freeze_frame_of is not None
            and frame.freeze_frame_of.root == e.id.root
        )
        assert frame.t.root == e.t.root
        actor = next(p for p in frame.players if p.id == e.player_id)
        where = (e.location.root[0].root, e.location.root[1].root)
        assert math.dist(xy(actor), where) <= 1.0, e.id
        checked += 1
    assert checked > 1000


def test_freeze_source_id_matches_pattern() -> None:
    assert freeze_source_id("ev-000123") == "ff-000123"
    common = json.loads((ROOT / "schemas/common.schema.json").read_text())
    assert re.match(
        common["$defs"]["sourceId"]["pattern"], freeze_source_id("ev-000123")
    )


def test_speed_and_jumps(capsys: pytest.CaptureFixture[str]) -> None:
    m = match()
    spans = [f[0] for f in m.frames]
    pinned: dict[int, set[str]] = {}
    for e in m.events:
        if e.player_id is not None:
            pinned.setdefault(bisect.bisect_left(spans, e.t.root), set()).add(
                e.player_id.root
            )
    resets = {bisect.bisect_left(spans, t) for t in m.sim.stats.reset_ticks}
    prev: dict[str, tuple[float, float]] = {}
    exceptions = steps = 0
    for i, frame in enumerate(m.frames):
        for pid, _, x, y, speed in rows(frame):
            assert speed <= MAX_SPEED_V1
            if pid in prev:
                steps += 1
                if math.dist((x, y), prev[pid]) > JUMP_BOUND:
                    assert pid in pinned.get(i, set()) or i in resets, (i, pid)
                    exceptions += 1
            prev[pid] = (x, y)
    with capsys.disabled():
        print(
            f"\njumps beyond the step bound (pinned actors, one reset): "
            f"{exceptions} of {steps} steps"
        )
    assert exceptions / steps < 0.001


def test_points_on_pitch_and_spacing() -> None:
    m = match()
    ts = [f[0] for f in m.frames]
    assert ts[0] == 0.0
    assert all(
        b - a == pytest.approx(FRAME_DT, abs=0.011) for a, b in itertools.pairwise(ts)
    )
    for f in m.frames[::10]:
        assert 0 <= f[2][0] <= 120 and 0 <= f[2][1] <= 80
        assert all(0 <= x <= 120 and 0 <= y <= 80 for _, _, x, y, _ in rows(f))


def test_red_card_removes_player_from_frames() -> None:
    m = match("red_card_flip", 1)
    card = next(
        e
        for e in m.events
        if e.type.value == "card" and e.outcome is not None and e.outcome.value == "red"
    )
    assert card.player_id is not None
    before = next(f for f in m.frames if f[0] < card.t.root - 1)
    after = next(f for f in m.frames if f[0] > card.t.root + 1)
    assert len(before[3]) == 22 and len(after[3]) == 21
    assert all(
        card.player_id.root not in f[3] for f in m.frames if f[0] > card.t.root + 0.01
    )


def test_sent_off_player_is_in_the_cards_freeze_frame_and_gone_after() -> None:
    m = match("red_card_flip", 3)
    card = next(
        e
        for e in m.events
        if e.type.value == "card" and e.outcome is not None and e.outcome.value == "red"
    )
    assert card.player_id is not None
    pid = card.player_id.root
    freeze = m.freezes[card.id.root]
    assert pid in [p.id.root for p in freeze.players] and len(freeze.players) == 22
    assert all(pid in f[3] for f in m.frames if f[0] <= card.t.root)
    assert all(pid not in f[3] for f in m.frames if f[0] > card.t.root)


def back_line(frames: list[Lite]) -> float:
    """Mean distance of the home side's deepest outfield player from its own goal."""
    return mean(
        min(x for pid, side, x, _, _ in rows(f) if side == "home" and pid != "home-01")
        for f in frames[::25]
    )


def ten_man_windows(seed: int) -> tuple[float, float, float, float]:
    """Median out-of-possession back line and hull area of the sent-off team: 15 min before the card, 30 min after."""
    m = match("red_card_flip", seed)
    card = next(
        e
        for e in m.events
        if e.type.value == "card" and e.outcome is not None and e.outcome.value == "red"
    )
    side = card.side.value
    before: list[tuple[float, float]] = []
    after: list[tuple[float, float]] = []
    for f in m.frames[::5]:
        if f[1] in ("", side):
            continue
        pts = [
            (x, y)
            for pid, s, x, y, _ in rows(f)
            if s == side and not pid.endswith("-01")
        ]
        window = (
            before
            if card.t.root - 900 <= f[0] < card.t.root
            else after
            if card.t.root < f[0] <= card.t.root + 1800
            else None
        )
        if window is not None:
            window.append((back_line_height(pts, side), hull_area(pts)))
    return (
        median(b for b, _ in before),
        median(b for b, _ in after),
        median(a for _, a in before),
        median(a for _, a in after),
    )


@pytest.mark.parametrize("seed", [1, 2, 3, 4])
def test_ten_man_team_drops_and_compresses_after_the_red_card(seed: int) -> None:
    back_before, back_after, area_before, area_after = ten_man_windows(seed)
    assert back_before - back_after >= 5.0
    assert area_after <= 0.85 * area_before


def test_out_of_possession_block_varies_frame_to_frame(
    capsys: pytest.CaptureFixture[str],
) -> None:
    lengths: list[float] = []
    areas: list[float] = []
    for story, seed in (("red_card_flip", 3), ("late_comeback", 3)):
        for f in match(story, seed).frames[::5]:
            for side in ("home", "away"):
                if f[1] in ("", side):
                    continue
                pts = [
                    (x, y)
                    for pid, s, x, y, _ in rows(f)
                    if s == side and not pid.endswith("-01")
                ]
                lengths.append(max(x for x, _ in pts) - min(x for x, _ in pts))
                areas.append(hull_area(pts))
    with capsys.disabled():
        print(
            f"\nframe-level std over {len(areas)} out-of-possession frames: "
            f"length {pstdev(lengths):.2f} m, area {pstdev(areas):.0f} m2"
        )
    assert pstdev(lengths) > 1.0 and pstdev(areas) > 50.0


def test_line_height_moves_the_back_line() -> None:
    high = match("late_comeback", 3, 0.85)
    low = match("late_comeback", 3, 0.2)
    assert back_line(high.frames) - back_line(low.frames) >= 8.0


def test_out_of_possession_shape_is_smaller_than_in_possession() -> None:
    m = match("late_comeback", 3)
    inside: list[float] = []
    outside: list[float] = []
    for f in m.frames[::10]:
        area = hull_area(
            [
                (x, y)
                for pid, side, x, y, _ in rows(f)
                if side == "home" and pid != "home-01"
            ]
        )
        (inside if f[1] == "home" else outside).append(area)
    assert mean(outside) < mean(inside)


def test_shape_is_the_only_module_with_slot_targets() -> None:
    names = [
        "LINE_SHIFT",
        "BALL_PULL",
        "LATERAL_PULL",
        "COMPACT_OUT",
        "WIDTH_IN",
        "WIDTH_OUT",
        "PUSH_IN",
    ]
    for path in (ROOT / "packages/sim/src/sim").glob("*.py"):
        if path.name == "shape.py":
            continue
        text = path.read_text()
        assert not [n for n in names if re.search(rf"\b{n}\b", text)], path.name


def test_stream_orders_events_and_frames() -> None:
    brief = make_brief(seed=2)
    last = -1.0
    n_events = n_frames = 0
    for item in iter_stream(brief):
        assert item.t.root >= last
        last = item.t.root
        if isinstance(item, Event):
            n_events += 1
        else:
            n_frames += 1
    events = generate(brief)
    assert n_events == len(events) and n_frames > 25000
    assert [e.id for e in iter_events(brief)][:3] == [e.id for e in events][:3]
    assert sum(1 for _ in iter_freeze_frames(brief, events)) == n_events


@pytest.mark.slow
def test_match_with_frames_generates_in_eight_seconds() -> None:
    brief = make_brief(seed=9)
    start = time.perf_counter()
    for _ in iter_stream(brief):
        pass
    assert time.perf_counter() - start < 8.0
