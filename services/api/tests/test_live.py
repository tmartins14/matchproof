import asyncio
import json
import re
import threading
from collections import Counter
from functools import lru_cache
from itertools import pairwise
from pathlib import Path
from typing import Any

import httpx
import pytest
from api import main
from api.live import (
    FOCUS_AFTER_S,
    FOCUS_BEFORE_S,
    FREEZE_HOLD_S,
    LOOKAHEAD_S,
    SPEED_FASTEST,
    SPEED_REAL_TIME,
    WIRE_FPS,
    NoPacer,
    _Control,
    merge_windows,
    run_live,
)
from contracts.models import MatchBrief, StreamMessage
from fastapi.testclient import TestClient
from intel.beats import detect_all
from intel.engine import extract_all
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012
from sim import generate
from sim.brief import DEFAULT_AWAY, DEFAULT_HOME, make_brief
from sim.positions import iter_frames, iter_freeze_frames

ROOT = Path(__file__).resolve().parents[3]
STORIES = ("red_card_flip", "late_comeback")


class FakePacer:
    """A clock that only moves when the stream waits on it."""

    def __init__(self) -> None:
        self.t = 0.0

    def now(self) -> float:
        return self.t

    async def sleep_until(self, real_t: float) -> None:
        self.t = max(self.t, real_t)


def brief_for(story: str, seed: int = 1) -> MatchBrief:
    return make_brief(DEFAULT_HOME, DEFAULT_AWAY, story, seed)


async def collect(
    brief: MatchBrief, speed: int, after_seq: int = -1
) -> list[tuple[float, StreamMessage]]:
    pacer = FakePacer()
    return [
        (pacer.t, m)
        async for m in run_live(brief, speed, pacer=pacer, after_seq=after_seq)
    ]


@lru_cache(maxsize=2)  # each run holds thousands of frame messages
def stream(story: str, speed: int) -> tuple[tuple[float, StreamMessage], ...]:
    return tuple(asyncio.run(collect(brief_for(story), speed)))


def dump(msg: StreamMessage) -> dict[str, Any]:
    out: dict[str, Any] = json.loads(
        msg.model_dump_json(by_alias=True, exclude_none=True)
    )
    return out


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
    return Draft202012Validator(
        schemas["stream_message.schema.json"], registry=registry
    )


def test_every_message_validates_against_the_schema() -> None:
    check = validator()
    messages = [m for _, m in stream("red_card_flip", SPEED_FASTEST)]
    for m in messages:
        check.validate(dump(m))
    assert {m.type.value for m in messages} >= {
        "status",
        "event",
        "frame",
        "fact",
        "beat",
    }


def test_unpaced_run_needs_no_clock() -> None:
    async def first() -> list[StreamMessage]:
        out = []
        async for m in run_live(
            brief_for("red_card_flip"), SPEED_FASTEST, pacer=NoPacer()
        ):
            out.append(m)
            if len(out) == 5:
                break
        return out

    assert [m.seq for m in asyncio.run(first())] == [0, 1, 2, 3, 4]


def test_ordering_and_facts_before_beats() -> None:
    messages = [m for _, m in stream("red_card_flip", SPEED_FASTEST)]
    assert [m.seq for m in messages] == list(range(len(messages)))
    times = [m.t.root for m in messages]
    assert times == sorted(times)
    seen: set[str] = set()
    beats = 0
    for m in messages:
        if m.type.value == "fact":
            seen.add(dump(m)["data"]["id"])
        elif m.type.value == "beat":
            beats += 1
            assert set(dump(m)["data"]["fact_ids"]) <= seen
    assert beats
    states = [dump(m)["data"]["state"] for m in messages if m.type.value == "status"]
    assert [x for x in states if x in ("pre_match", "half_time", "full_time")] == [
        "pre_match",
        "half_time",
        "full_time",
    ]


def test_window_desk_and_beat_facts_only() -> None:
    messages = [m for _, m in stream("red_card_flip", SPEED_FASTEST)]
    cited = {
        f
        for m in messages
        if m.type.value == "beat"
        for f in dump(m)["data"]["fact_ids"]
    }
    facts = [dump(m)["data"] for m in messages if m.type.value == "fact"]
    windows = [
        f
        for f in facts
        if len(f["source_ids"]) == 1 and f["source_ids"][0].startswith("win-")
    ]
    desk = [
        f
        for f in facts
        if f["extractor"]["name"] in ("extract_running", "extract_momentum")
    ]
    assert len(facts) < 1200  # the registry holds about 10,800
    assert {f["id"] for f in facts} == cited | {f["id"] for f in windows} | {
        f["id"] for f in desk
    }
    assert sum(f["name"].startswith("momentum(") for f in desk) == 18


def test_every_fact_on_the_stream_has_a_label() -> None:
    messages = [m for _, m in stream("red_card_flip", SPEED_FASTEST)]
    facts = [dump(m)["data"] for m in messages if m.type.value == "fact"]
    assert facts
    assert [f["name"] for f in facts if not f.get("label")] == []
    assert not [
        f["label"] for f in facts if re.search(r"t\d+\.\d+|match time", f["label"])
    ]


@pytest.mark.slow
@pytest.mark.parametrize("story", STORIES)
def test_stream_beats_equal_batch(story: str) -> None:
    brief = brief_for(story)
    events = generate(brief)
    frames = list(iter_frames(brief, events))
    freeze = list(iter_freeze_frames(brief, events))
    batch = detect_all(events, frames, freeze, extract_all(events, frames, freeze))
    live = [
        dump(m)["data"]
        for _, m in stream(story, SPEED_FASTEST)
        if m.type.value == "beat"
    ]
    expected = [
        json.loads(b.model_dump_json(by_alias=True, exclude_none=True)) for b in batch
    ]
    assert live == expected


@pytest.mark.parametrize(
    "speed", [pytest.param(SPEED_REAL_TIME, marks=pytest.mark.slow), SPEED_FASTEST]
)
def test_frame_rate_on_the_wire_is_capped(speed: int) -> None:
    per_second = Counter(
        int(t) for t, m in stream("red_card_flip", speed) if m.type.value == "frame"
    )
    assert per_second
    assert max(per_second.values()) <= WIRE_FPS


def test_resume_continues_after_the_last_seq() -> None:
    full = [m for _, m in stream("red_card_flip", SPEED_FASTEST)]
    cut = len(full) // 2
    resumed = [
        m
        for _, m in asyncio.run(collect(brief_for("red_card_flip"), SPEED_FASTEST, cut))
    ]
    assert resumed[0].seq == cut + 1
    assert [dump(m) for m in resumed] == [dump(m) for m in full[cut + 1 :]]


def test_endpoint_resumes_with_last_event_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "make_pacer", NoPacer)
    client = TestClient(main.app)
    match_id = client.post(
        "/matches", json={"story": "red_card_flip", "seed": 1}
    ).json()["match_id"]
    url = f"/matches/{match_id}/stream?speed={SPEED_FASTEST}"
    full = client.get(url)
    assert full.headers["content-type"].startswith("text/event-stream")
    chunks = [c for c in full.text.split("\n\n") if c.startswith("id: ")]
    assert chunks[0].startswith("id: 0\n")
    cut = 100
    tail = client.get(url, headers={"Last-Event-ID": str(cut)})
    resumed = [c for c in tail.text.split("\n\n") if c.startswith("id: ")]
    assert resumed == chunks[cut + 1 :]


def test_post_matches_validates() -> None:
    client = TestClient(main.app)
    assert client.post(
        "/matches", json={"story": "red_card_flip", "seed": 2}
    ).json() == {"match_id": "m-red-card-flip-2"}
    assert client.post("/matches", json={"story": "no_such_story"}).status_code == 422
    assert client.post("/matches", json={"seed": 3, "home": "nope"}).status_code == 422
    brief = brief_for("late_comeback", 5).model_dump(
        mode="json", by_alias=True, exclude_none=True
    )
    assert client.post("/matches", json=brief).json() == {
        "match_id": "m-late-comeback-5"
    }
    del brief["storyline"]
    assert client.post("/matches", json=brief).status_code == 422


def test_unknown_match_and_fact_are_404() -> None:
    client = TestClient(main.app)
    assert client.get("/matches/m-nope/facts/fx-x").status_code == 404
    assert client.get("/matches/m-nope/stream").status_code == 404
    match_id = client.post(
        "/matches", json={"story": "smash_and_grab", "seed": 1}
    ).json()["match_id"]
    assert client.get(f"/matches/{match_id}/facts/fx-no-such-fact").status_code == 404
    found = client.get(f"/matches/{match_id}/facts/fx-possession_share-home-match")
    assert found.status_code == 200
    assert found.json()["id"] == "fx-possession_share-home-match"


def test_third_concurrent_stream_from_one_client_gets_429(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = asyncio.Event()

    async def held(*args: Any, **kwargs: Any) -> Any:
        yield StreamMessage.model_validate(
            {"seq": 0, "type": "status", "t": 0, "data": {"state": "live"}}
        )
        await release.wait()

    monkeypatch.setattr(main, "run_live", held)

    async def scenario() -> list[int]:
        transport = httpx.ASGITransport(app=main.app, client=("203.0.113.9", 5000))
        async with httpx.AsyncClient(
            transport=transport, base_url="http://t"
        ) as client:
            made = await client.post(
                "/matches", json={"story": "late_comeback", "seed": 1}
            )
            url = f"/matches/{made.json()['match_id']}/stream"
            first = asyncio.create_task(client.get(url))
            second = asyncio.create_task(client.get(url))
            while main._streams["203.0.113.9"] < 2:
                await asyncio.sleep(0.01)
            third = await client.get(url)
            release.set()
            done = await asyncio.gather(first, second)
            return [third.status_code, *(r.status_code for r in done)]

    assert asyncio.run(scenario()) == [429, 200, 200]
    assert main._streams["203.0.113.9"] == 0


def test_windows_around_anchors_merge_when_they_overlap() -> None:
    assert merge_windows([200.0, 100.0, 110.0]) == [
        (100.0 - FOCUS_BEFORE_S, 110.0 + FOCUS_AFTER_S),
        (200.0 - FOCUS_BEFORE_S, 200.0 + FOCUS_AFTER_S),
    ]
    assert merge_windows([4.0]) == [(0.0, 4.0 + FOCUS_AFTER_S)]


def test_focus_freeze_then_beat() -> None:
    timed = list(stream("red_card_flip", SPEED_FASTEST))
    freezes = [
        i
        for i, (_, m) in enumerate(timed)
        if m.type.value == "status" and dump(m)["data"]["state"] == "freeze"
    ]
    assert freezes
    for i in freezes:
        status = dump(timed[i][1])["data"]
        assert "speed" not in status
        event_id = status["event_id"]
        # the freeze frame follows its status at the same second, and the beat only after the hold
        frozen = dump(timed[i + 1][1])
        assert (
            frozen["type"] == "frame" and frozen["data"]["freeze_frame_of"] == event_id
        )
        beat_at = next(
            t
            for t, m in timed[i + 2 :]
            if m.type.value == "beat" and dump(m)["data"]["anchor_event_id"] == event_id
        )
        assert beat_at - timed[i + 1][0] >= FREEZE_HOLD_S
        # a focus status opens the window; it carries nothing about what comes
        start = max(
            j
            for j in range(i)
            if timed[j][1].type.value == "status"
            and dump(timed[j][1])["data"]["state"] == "focus"
        )
        assert dump(timed[start][1])["data"] == {"state": "focus"}
        frames = [
            dump(m)["data"]["t"] for _, m in timed[start:i] if m.type.value == "frame"
        ]
        assert len(frames) >= 2
        assert all(abs((b - a) - 0.2) < 0.011 for a, b in pairwise(frames))
        assert (
            dump(timed[i][1])["t"] - dump(timed[start][1])["t"] <= FOCUS_BEFORE_S + 0.01
        )


@pytest.mark.slow
def test_content_does_not_depend_on_the_clock() -> None:
    unpaced = asyncio.run(collect_unpaced(brief_for("red_card_flip"), SPEED_FASTEST))
    assert [dump(m) for m in unpaced] == [
        dump(m) for _, m in stream("red_card_flip", SPEED_FASTEST)
    ]


async def collect_unpaced(brief: MatchBrief, speed: int) -> list[StreamMessage]:
    return [m async for m in run_live(brief, speed, pacer=NoPacer())]


def test_pipeline_waits_for_playback() -> None:
    control = _Control()
    allowed: list[bool] = []
    worker = threading.Thread(
        target=lambda: allowed.append(control.wait_until_allowed(LOOKAHEAD_S + 10))
    )
    worker.start()
    worker.join(0.2)
    assert worker.is_alive()  # beyond the lookahead: blocked
    control.advance(20.0)
    worker.join(2.0)
    assert allowed == [True]
    stopped: list[bool] = []
    blocked = threading.Thread(
        target=lambda: stopped.append(control.wait_until_allowed(10_000.0))
    )
    blocked.start()
    control.cancel()
    blocked.join(2.0)
    assert stopped == [False]
