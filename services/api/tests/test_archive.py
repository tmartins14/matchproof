import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from api import main
from api.archiving import save_now, schedule_save
from api.live import NoPacer, run_live
from api.matchdata import store
from fastapi.testclient import TestClient
from intel.registry import FactRegistry
from jsonschema import Draft202012Validator
from mcp_match import FileArchive
from mcp_match.persist import save_match
from mcp_match.store import MatchRecord
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012
from sim.brief import make_brief

ROOT = Path(__file__).resolve().parents[3]
SHORT_S = 420.0  # seven match minutes: enough for events, facts and a beat or two


def claim_graph_validator() -> Draft202012Validator:
    schemas = {
        p.name: json.loads(p.read_text())
        for p in (ROOT / "schemas").glob("*.schema.json")
    }
    registry: Registry[Any] = Registry()
    for s in schemas.values():
        registry = registry.with_resource(
            str(s["$id"]), Resource.from_contents(s, DRAFT202012)
        )
    return Draft202012Validator(schemas["claim_graph.schema.json"], registry=registry)


def play_short(seed: int = 5) -> str:
    brief = make_brief(storyline_id="late_comeback", seed=seed)

    async def go() -> None:
        async for _ in run_live(brief, pacer=NoPacer(), store=store, until_s=SHORT_S):
            pass

    asyncio.run(go())
    return brief.match_id


def test_a_short_match_is_saved_and_its_claim_graph_validates(
    archive_in_tmp: FileArchive,
) -> None:
    match_id = play_short()
    brief = store.brief(match_id)
    assert save_now(store, brief, {"match_id": match_id}, [], {"usage": {}}) is True
    assert save_now(store, brief, {}, [], {}) is False  # already archived: left alone

    graph = json.loads(archive_in_tmp.get(match_id, "claim_graph.json"))
    claim_graph_validator().validate(graph)
    manifest = json.loads(archive_in_tmp.get(match_id, "manifest.json"))
    names = {f["name"] for f in manifest["files"]}
    assert {
        "brief.json",
        "events.jsonl.gz",
        "facts.jsonl.gz",
        "beats.jsonl",
        "claim_graph.json",
        "audit.json",
        "producer_log.json",
        "usage.json",
        "frames.jsonl.gz",
        "freeze.jsonl.gz",
    } == names


def test_schedule_save_runs_in_the_background(archive_in_tmp: FileArchive) -> None:
    match_id = play_short(6)
    brief = store.brief(match_id)

    async def go() -> None:
        schedule_save(store, brief, None)
        from api import archiving

        await asyncio.gather(*archiving._tasks)

    asyncio.run(go())
    assert match_id in archive_in_tmp.matches()


def seed_archive(archive: FileArchive) -> str:
    record = MatchRecord(make_brief(seed=42), FactRegistry())
    save_match(
        archive,
        record,
        frames=[],
        audit={"match_id": record.brief.match_id, "claims": 0},
        producer_log=[{"beat_id": "bt-1", "narrate": True}],
        usage={},
        git_sha="abc",
        created_at=datetime(2026, 10, 23, tzinfo=UTC),
    )
    return record.brief.match_id


def test_archived_matches_are_listed_and_served_after_a_restart(
    archive_in_tmp: FileArchive,
) -> None:
    match_id = seed_archive(archive_in_tmp)
    main._briefs.clear()
    store._records.clear()  # a fresh process
    client = TestClient(main.app)

    listed = client.get("/matches").json()
    assert listed == [
        {
            "match_id": match_id,
            "storyline": "late_comeback",
            "score": {"home": 0, "away": 0},
            "created_at": "2026-10-23T00:00:00+00:00",
            "claims": {"total": 0},
        }
    ]
    assert client.get(f"/matches/{match_id}/audit").json()["match_id"] == match_id
    assert client.get(f"/matches/{match_id}/producer-log").json() == [
        {"beat_id": "bt-1", "narrate": True}
    ]
    assert client.get(f"/matches/{match_id}/facts/fx-nothing").status_code == 404
    assert client.get("/matches/m-unknown-1/audit").status_code == 404
