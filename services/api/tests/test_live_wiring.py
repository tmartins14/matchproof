import asyncio
import re
from functools import lru_cache

import pytest
from api import main
from api.live import NoPacer, run_live
from api.matchdata import store
from contracts.models import Beat, Event, Status, StreamMessage
from fastapi.testclient import TestClient
from intel.score import is_goal, match_score
from mcp_match import FileArchive
from sim.brief import make_brief


@lru_cache(maxsize=1)
def played() -> tuple[StreamMessage, ...]:
    return tuple(play())


def play(seed: int = 3, until_s: float | None = None) -> list[StreamMessage]:
    brief = make_brief(storyline_id="red_card_flip", seed=seed)

    async def go() -> list[StreamMessage]:
        return [m async for m in run_live(brief, pacer=NoPacer(), until_s=until_s)]

    return asyncio.run(go())


def test_preflight_from_an_allowed_origin_passes() -> None:
    reply = TestClient(main.app).options(
        "/matches",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert reply.status_code == 200
    assert reply.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "POST" in reply.headers["access-control-allow-methods"]


def test_preflight_from_another_origin_is_refused() -> None:
    reply = TestClient(main.app).options(
        "/matches",
        headers={
            "Origin": "https://elsewhere.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert reply.status_code == 400
    assert "access-control-allow-origin" not in reply.headers


def test_web_origins_come_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WEB_ORIGINS", raising=False)
    assert main.web_origins() == ["http://localhost:3000"]
    monkeypatch.setenv("WEB_ORIGINS", "https://a.example, https://b.example")
    assert main.web_origins() == ["https://a.example", "https://b.example"]


def test_a_score_status_follows_every_goal_and_full_time_carries_the_score() -> None:
    messages = played()
    events = [m.data for m in messages if isinstance(m.data, Event)]
    goals = [e for e in events if is_goal(e)]
    assert goals
    scores = [
        m.data
        for m in messages
        if isinstance(m.data, Status) and m.data.state.value == "score"
    ]
    assert [(s.score.home, s.score.away) for s in scores if s.score] == [
        match_score(events, g.t.root) for g in goals
    ]
    index = {m.seq: m for m in messages}
    for g, s in zip(goals, [m for m in messages if m.data in scores], strict=True):
        before = index[s.seq - 1]
        assert before.data == g  # the score status comes straight after its goal
    last = messages[-1].data
    assert isinstance(last, Status) and last.state.value == "full_time"
    assert last.score is not None
    assert (last.score.home, last.score.away) == match_score(events)


def test_beats_carry_their_highlight() -> None:
    messages = played()
    events = {m.data.id.root: m.data for m in messages if isinstance(m.data, Event)}
    beats = [m.data for m in messages if isinstance(m.data, Beat)]
    assert beats
    for beat in beats:
        anchor = events[beat.anchor_event_id.root]
        if beat.kind.value == "territorial_spell":
            assert beat.highlight is not None and beat.highlight.zone is not None
            zone = beat.highlight.zone
            assert (zone.x_from, zone.x_to) == (
                (60.0, 120.0)
                if beat.side and beat.side.value == "home"
                else (0.0, 60.0)
            )
        elif anchor.player_id:
            assert beat.highlight is not None
            assert [p.root for p in beat.highlight.player_ids or []] == [
                anchor.player_id.root
            ]


def test_sources_route_answers_each_kind_and_404s_an_unknown_id() -> None:
    client = TestClient(main.app)
    match_id = client.post(
        "/matches", json={"story": "red_card_flip", "seed": 3}
    ).json()["match_id"]
    aggregate_id = next(iter(main.match_registry(match_id).aggregates))
    got = client.get(f"/matches/{match_id}/sources/{aggregate_id}").json()
    assert got["kind"] == "aggregate"
    assert got["description"] == main.match_registry(match_id).aggregates[aggregate_id]
    assert got["label"] and "1 Hz" not in got["label"] and "ev-" not in got["label"]

    window = client.get(f"/matches/{match_id}/sources/win-01").json()
    assert window["kind"] == "window" and window["t_from"] == 0.0
    assert window["t_to"] == 900.0
    assert window["label"] == "Play from 0:00 to 15:00"

    freeze = client.get(f"/matches/{match_id}/sources/ff-000123").json()
    assert freeze["kind"] == "freeze_frame" and freeze["event_id"] == "ev-000123"
    assert freeze["label"].startswith("Where everyone stood at ")

    assert client.get(f"/matches/{match_id}/sources/nope-1").status_code == 404
    assert client.get("/matches/unknown/sources/win-01").status_code == 404


def test_any_brief_under_an_archived_id_gets_a_fresh_id(
    archive_in_tmp: FileArchive,
) -> None:
    from test_archive import seed_archive

    match_id = seed_archive(archive_in_tmp)
    main._briefs.clear()
    store._records.clear()  # a fresh process: the id is only in the archive
    archived = store.brief(match_id)
    same_id = main.store_brief(
        archived
    )  # even an identical brief does not rejoin a finished match
    assert same_id != match_id and re.fullmatch(rf"{match_id}-r[0-9a-f]{{6}}", same_id)
    edited = archived.model_copy(update={"seed": archived.seed + 1})
    new_id = main.store_brief(edited)
    assert new_id != match_id and re.fullmatch(rf"{match_id}-r[0-9a-f]{{6}}", new_id)
    assert main.brief_of(match_id) == archived
