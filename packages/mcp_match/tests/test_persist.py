import asyncio
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import pytest
from azure.core.exceptions import ResourceNotFoundError
from contracts.models import Audit, Claim, PositionFrame
from helpers import call, client_for, fill, finished, validator
from intel.registry import FactRegistry
from mcp_match import (
    ArchiveMissing,
    BlobArchive,
    FileArchive,
    InMemoryMatchStore,
    MatchArchive,
    UnknownMatch,
)
from mcp_match.persist import (
    BEATS,
    FRAMES,
    MANIFEST,
    list_manifests,
    load_frames,
    load_json,
    save_match,
)
from mcp_match.store import MatchRecord
from sim.brief import make_brief
from sim.positions import iter_frames

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)


def claim_for(store: InMemoryMatchStore, match_id: str) -> tuple[str, Claim]:
    beat = next(b for b in store.beats(match_id) if b.fact_ids)
    fact_id = beat.fact_ids[0].root
    claim = Claim.model_validate(
        {
            "id": "cl-001-01",
            "beat_id": beat.id.root,
            "lang": "en",
            "text": "A moment on the pitch.",
            "fact_ids": [fact_id],
            "numbers": [],
            "verdict": "verified",
        }
    )
    return beat.id.root, claim


@lru_cache(maxsize=1)
def filled() -> tuple[InMemoryMatchStore, str]:
    """A finished match with one claim and its audit. Cached: read it, do not change it."""
    store = InMemoryMatchStore()
    match_id = fill(store, "red_card_flip", 3)
    beat_id, claim = claim_for(store, match_id)
    store.put_claims(match_id, beat_id, [claim])
    store.put_audit(
        match_id,
        "cl-001-01",
        Audit.model_validate({"deployment": "judge-grok", "outcome": "agree"}),
    )
    return store, match_id


@lru_cache(maxsize=1)
def frames_of(match_id: str) -> list[PositionFrame]:
    store, _ = filled()
    record = store.record(match_id)
    return list(iter_frames(record.brief, record.events))


def save(
    archive: MatchArchive, store: InMemoryMatchStore, match_id: str
) -> dict[str, Any]:
    record = store.record(match_id)
    return save_match(
        archive,
        record,
        frames=frames_of(match_id),
        audit={"match_id": match_id, "claims": 1},
        producer_log=[{"beat_id": "bt-1", "narrate": True}],
        usage={"usage": {}, "cost": "prices not set"},
        git_sha="abc1234",
        created_at=NOW,
    )


class Recorder(FileArchive):
    """Remembers the order of writes; can fail on the nth."""

    def __init__(self, root: Path, fail_on: int | None = None) -> None:
        super().__init__(root)
        self.order: list[str] = []
        self.fail_on = fail_on

    def put(self, match_id: str, name: str, data: bytes) -> None:
        if self.fail_on is not None and len(self.order) == self.fail_on:
            raise OSError("disk full")
        self.order.append(name)
        super().put(match_id, name, data)


def test_file_archive_round_trip_returns_an_identical_match(tmp_path: Path) -> None:
    archive = FileArchive(tmp_path)
    store, match_id = filled()
    original = store.record(match_id)
    save(archive, store, match_id)

    fresh = InMemoryMatchStore(archive=archive)
    loaded = fresh.record(match_id)
    assert loaded.brief == original.brief
    assert loaded.events == original.events
    assert loaded.beats == original.beats
    assert loaded.registry == original.registry
    assert loaded.freeze_frames == original.freeze_frames
    assert loaded.claims == original.claims
    assert loaded.claims[next(iter(loaded.claims))][0].audit is not None
    assert loaded.finished
    frames = list(load_frames(archive, match_id))
    assert frames == frames_of(match_id)
    assert all(isinstance(f, PositionFrame) for f in frames)
    assert load_json(archive, match_id, "audit.json")["claims"] == 1
    assert load_json(archive, match_id, "producer_log.json")[0]["beat_id"] == "bt-1"


def test_the_claim_graph_validates_against_its_schema(tmp_path: Path) -> None:
    archive = FileArchive(tmp_path)
    store, match_id = filled()
    save(archive, store, match_id)
    graph = json.loads(archive.get(match_id, "claim_graph.json"))
    validator("claim_graph").validate(graph)
    assert graph["final_score"] == {"home": 2, "away": 0}
    assert len(graph["claims"]) == 1


def test_the_manifest_is_written_last_and_lists_the_files(tmp_path: Path) -> None:
    archive = Recorder(tmp_path)
    store, match_id = filled()
    manifest = save(archive, store, match_id)
    assert archive.order[-1] == MANIFEST
    assert archive.order.count(MANIFEST) == 1
    assert [f["name"] for f in manifest["files"]] == archive.order[:-1]
    sizes = {f["name"]: f["size"] for f in manifest["files"]}
    assert all(len(archive.get(match_id, n)) == s for n, s in sizes.items())
    assert manifest["git_sha"] == "abc1234"
    assert manifest["created_at"] == NOW.isoformat()
    assert manifest["schema_versions"]["claim_graph"] == "1.0.0"
    assert manifest["claims"] == {"total": 1, "verified": 1}
    assert manifest["storyline"] == "red_card_flip"


def test_a_save_that_fails_midway_is_never_listed_or_read(tmp_path: Path) -> None:
    archive = Recorder(tmp_path, fail_on=4)
    store, match_id = filled()
    with pytest.raises(OSError):
        save(archive, store, match_id)
    assert MANIFEST not in archive.order
    assert (tmp_path / match_id / BEATS).exists() or archive.order  # files may be there
    assert archive.matches() == []
    assert list_manifests(archive) == []
    with pytest.raises(UnknownMatch):
        InMemoryMatchStore(archive=archive).brief(match_id)
    with pytest.raises(ArchiveMissing):
        list(load_frames(archive, match_id))


def stub(seed: int) -> MatchRecord:
    """A match with no play in it: cheap to make, enough to fill a slot or a listing."""
    return MatchRecord(make_brief(seed=seed), FactRegistry())


def test_an_evicted_match_reloads_through_mcp_get_fact(tmp_path: Path) -> None:
    archive = FileArchive(tmp_path)
    a_store, first = filled()
    save(archive, a_store, first)
    fact_id = a_store.beats(first)[0].fact_ids[0].root

    store = InMemoryMatchStore(max_matches=1, archive=archive)
    store.brief(first)
    other = stub(9)
    store.begin(other.brief, other.registry)
    assert other.brief.match_id in store and first not in store

    async def scenario() -> None:
        async with client_for(store, False) as s:
            fact = await call(s, "get_fact", match_id=first, fact_id=fact_id)
            assert fact["id"] == fact_id
            assert (await call(s, "get_brief", match_id=first))["match_id"] == first

    asyncio.run(scenario())
    assert first in store and other.brief.match_id not in store
    with pytest.raises(UnknownMatch):
        store.brief("m-nothing-0")


def test_list_manifests_newest_first(tmp_path: Path) -> None:
    archive = FileArchive(tmp_path)
    older, newer = stub(1), stub(2)
    for record, day in ((older, 23), (newer, 24)):
        save_match(
            archive,
            record,
            frames=[],
            audit={},
            producer_log=[],
            usage={},
            git_sha="x",
            created_at=datetime(2026, 10, day, tzinfo=UTC),
        )
    listed = list_manifests(archive)
    assert [m["match_id"] for m in listed] == [
        newer.brief.match_id,
        older.brief.match_id,
    ]
    assert listed[0]["final_score"] == {"home": 0, "away": 0}


# ---- Blob, against a fake container ------------------------------------------------------------
class FakeBlob:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def readall(self) -> bytes:
        return self._data


class FakeListed:
    def __init__(self, name: str) -> None:
        self.name = name


class FakeContainer:
    def __init__(self) -> None:
        self.blobs: dict[str, bytes] = {}
        self.overwrites: list[bool] = []

    def upload_blob(self, name: str, data: bytes, overwrite: bool = False) -> None:
        self.overwrites.append(overwrite)
        self.blobs[name] = data

    def download_blob(self, name: str) -> FakeBlob:
        if name not in self.blobs:
            raise ResourceNotFoundError("BlobNotFound")
        return FakeBlob(self.blobs[name])

    def list_blobs(self) -> Iterator[FakeListed]:
        return (FakeListed(n) for n in sorted(self.blobs))


def test_blob_archive_round_trip_against_a_fake_container() -> None:
    container = FakeContainer()
    archive = BlobArchive(container)  # type: ignore[arg-type]
    store, match_id = filled()
    save(archive, store, match_id)
    assert f"{match_id}/{MANIFEST}" in container.blobs
    assert f"{match_id}/{FRAMES}" in container.blobs
    assert all(container.overwrites)
    assert archive.matches() == [match_id]
    assert (
        InMemoryMatchStore(archive=archive).record(match_id).events
        == store.record(match_id).events
    )
    with pytest.raises(ArchiveMissing):
        archive.get(match_id, "nope.json")


def test_blob_archive_lists_only_finished_matches() -> None:
    container = FakeContainer()
    archive = BlobArchive(container)  # type: ignore[arg-type]
    container.blobs["m-a-1/brief.json"] = b"{}"
    container.blobs["m-b-1/manifest.json"] = b"{}"
    assert archive.matches() == ["m-b-1"]


def test_the_shared_finished_match_is_untouched_by_all_this() -> None:
    store, match_id = finished()
    assert store.archive is None and store.brief(match_id)
