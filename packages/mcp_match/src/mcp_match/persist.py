"""Finished matches on disk or in Blob, and back.

One folder per match, `<match_id>/`:

    brief.json            the MatchBrief
    events.jsonl.gz       every event
    facts.jsonl.gz        the fact registry; the first line is {"aggregates": {...}}
    beats.jsonl           the detected beats
    claim_graph.json      ClaimGraph (schema claim_graph.schema.json), claims with their audits
    audit.json            the second model's summary, as /matches/{id}/audit serves it
    producer_log.json     the Producer's decisions, as /matches/{id}/producer-log serves them
    usage.json            tokens per role and model, and cost if prices are set
    frames.jsonl.gz       position frames at 5 Hz
    freeze.jsonl.gz       one {"event_id", "frame"} per freeze frame
    manifest.json         written last: files and sizes, schema versions, git SHA, created time

The manifest is the commit marker. A match without one is a save that did not finish: it is not
listed and not loaded. Storage is managed identity only (DefaultAzureCredential); there are no keys.
"""

import gzip
import io
import json
import os
from collections.abc import Iterable, Iterator, Mapping
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from azure.core.exceptions import ResourceNotFoundError
from contracts.models import (
    Beat,
    ClaimGraph,
    Event,
    Fact,
    MatchBrief,
    PositionFrame,
)
from intel.registry import FactRegistry

if TYPE_CHECKING:
    from azure.storage.blob import ContainerClient

    from .store import MatchRecord

LAYOUT_VERSION = "1"
CLAIM_GRAPH_VERSION = "1.0.0"
CONTAINER = "matches"
MANIFEST = "manifest.json"
DEFAULT_DIR = "data/archive"

BRIEF = "brief.json"
EVENTS = "events.jsonl.gz"
FACTS = "facts.jsonl.gz"
BEATS = "beats.jsonl"
CLAIM_GRAPH = "claim_graph.json"
AUDIT = "audit.json"
PRODUCER_LOG = "producer_log.json"
USAGE = "usage.json"
FRAMES = "frames.jsonl.gz"
FREEZE = "freeze.jsonl.gz"


class ArchiveMissing(KeyError):
    """No such file (or no finished match) in the archive."""


class MatchArchive(Protocol):
    """Named blobs per match. Implementations know nothing about what is in them."""

    def put(self, match_id: str, name: str, data: bytes) -> None: ...

    def get(self, match_id: str, name: str) -> bytes:
        """The file's bytes; ArchiveMissing if there is none."""
        ...

    def matches(self) -> list[str]:
        """Ids of matches that have a manifest, that is, whose save finished."""
        ...


class FileArchive:
    """Local folders under `root`. A file is written whole, then renamed into place."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def put(self, match_id: str, name: str, data: bytes) -> None:
        folder = self.root / match_id
        folder.mkdir(parents=True, exist_ok=True)
        tmp = folder / f".{name}.tmp"
        tmp.write_bytes(data)
        tmp.replace(folder / name)

    def get(self, match_id: str, name: str) -> bytes:
        try:
            return (self.root / match_id / name).read_bytes()
        except FileNotFoundError as exc:
            raise ArchiveMissing(f"{match_id}/{name}") from exc

    def matches(self) -> list[str]:
        if not self.root.is_dir():
            return []
        return sorted(p.parent.name for p in self.root.glob(f"*/{MANIFEST}"))


class BlobArchive:
    """The `matches` container of the storage account, reached with DefaultAzureCredential."""

    def __init__(self, container: "ContainerClient") -> None:
        self._container = container

    @classmethod
    def from_env(cls) -> "BlobArchive":
        from azure.identity import DefaultAzureCredential
        from azure.storage.blob import BlobServiceClient

        account = os.environ.get("AZURE_STORAGE_ACCOUNT")
        if not account:
            raise RuntimeError("AZURE_STORAGE_ACCOUNT is not set")
        service = BlobServiceClient(
            f"https://{account}.blob.core.windows.net",
            credential=DefaultAzureCredential(),
        )
        return cls(service.get_container_client(CONTAINER))

    def put(self, match_id: str, name: str, data: bytes) -> None:
        self._container.upload_blob(f"{match_id}/{name}", data, overwrite=True)

    def get(self, match_id: str, name: str) -> bytes:
        try:
            data: bytes = self._container.download_blob(f"{match_id}/{name}").readall()
        except ResourceNotFoundError as exc:
            raise ArchiveMissing(f"{match_id}/{name}") from exc
        return data

    def matches(self) -> list[str]:
        suffix = f"/{MANIFEST}"
        names = (b.name for b in self._container.list_blobs())
        return sorted(n[: -len(suffix)] for n in names if n.endswith(suffix))


def archive_from_env() -> MatchArchive:
    """MATCH_ARCHIVE=file (the default, under MATCH_ARCHIVE_DIR) or blob."""
    kind = os.environ.get("MATCH_ARCHIVE", "file")
    if kind == "file":
        return FileArchive(Path(os.environ.get("MATCH_ARCHIVE_DIR", DEFAULT_DIR)))
    if kind == "blob":
        return BlobArchive.from_env()
    raise ValueError(f"MATCH_ARCHIVE must be file or blob, not {kind!r}")


# ---- writing ---------------------------------------------------------------------------------
def _json(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False, indent=1).encode("utf-8")


def _lines(lines: Iterable[str], compress: bool) -> bytes:
    """Newline-delimited text, gzipped without a timestamp so the same match gives the same bytes."""
    out = io.BytesIO()
    if compress:
        with gzip.GzipFile(fileobj=out, mode="wb", mtime=0) as gz:
            for line in lines:
                gz.write(line.encode("utf-8") + b"\n")
    else:
        for line in lines:
            out.write(line.encode("utf-8") + b"\n")
    return out.getvalue()


def _dump(model: Any) -> str:
    out: str = model.model_dump_json(by_alias=True, exclude_none=True)
    return out


def final_score(events: Iterable[Event]) -> dict[str, int]:
    score = {"home": 0, "away": 0}
    for e in events:
        if (
            e.type.value == "shot"
            and e.outcome is not None
            and e.outcome.value == "goal"
        ):
            score[e.side.value] += 1
    return score


def build_claim_graph(record: "MatchRecord", created_at: datetime) -> ClaimGraph:
    """The record as a ClaimGraph. Raises pydantic.ValidationError if it breaks the contract."""
    return ClaimGraph.model_validate(
        {
            "schema_version": CLAIM_GRAPH_VERSION,
            "match_id": record.brief.match_id,
            "brief": record.brief.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
            "generated_at": created_at,
            "final_score": final_score(record.events),
            "facts": [
                f.model_dump(mode="json", by_alias=True, exclude_none=True)
                for f in record.registry.all()
            ],
            "beats": [
                b.model_dump(mode="json", by_alias=True, exclude_none=True)
                for b in record.beats
            ],
            "claims": [
                c.model_dump(mode="json", by_alias=True, exclude_none=True)
                for claims in record.claims.values()
                for c in claims
            ],
            "overlays": [],
        }
    )


def save_match(
    archive: MatchArchive,
    record: "MatchRecord",
    *,
    frames: Iterable[PositionFrame],
    audit: Mapping[str, Any],
    producer_log: list[dict[str, Any]],
    usage: Mapping[str, Any],
    git_sha: str,
    created_at: datetime,
) -> dict[str, Any]:
    """Write every file, then the manifest. Returns the manifest. Nothing is half-visible: until the
    manifest is there the match is not listed or loaded."""
    match_id = record.brief.match_id
    graph = build_claim_graph(record, created_at)
    header = json.dumps({"aggregates": record.registry.aggregates}, sort_keys=True)
    files: dict[str, bytes] = {
        BRIEF: _json(
            record.brief.model_dump(mode="json", by_alias=True, exclude_none=True)
        ),
        EVENTS: _lines((_dump(e) for e in record.events), True),
        FACTS: _lines([header, *(_dump(f) for f in record.registry.all())], True),
        BEATS: _lines((_dump(b) for b in record.beats), False),
        CLAIM_GRAPH: graph.model_dump_json(by_alias=True, exclude_none=True).encode(
            "utf-8"
        ),
        AUDIT: _json(audit),
        PRODUCER_LOG: _json(producer_log),
        USAGE: _json(usage),
        FRAMES: _lines((_dump(f) for f in frames), True),
        FREEZE: _lines(
            (
                json.dumps({"event_id": eid, "frame": json.loads(_dump(f))})
                for eid, f in record.freeze_frames.items()
            ),
            True,
        ),
    }
    for name, data in files.items():
        archive.put(match_id, name, data)
    verdicts: dict[str, int] = {}
    for c in graph.claims:
        verdicts[c.verdict.value] = verdicts.get(c.verdict.value, 0) + 1
    manifest = {
        "match_id": match_id,
        "created_at": created_at.isoformat(),
        "git_sha": git_sha,
        "layout_version": LAYOUT_VERSION,
        "schema_versions": {"claim_graph": CLAIM_GRAPH_VERSION},
        "storyline": record.brief.storyline.id.value,
        "final_score": graph.final_score.model_dump() if graph.final_score else None,
        "claims": {"total": len(graph.claims), **verdicts},
        "beats": len(record.beats),
        "files": [{"name": n, "size": len(d)} for n, d in files.items()],
    }
    archive.put(match_id, MANIFEST, _json(manifest))
    return manifest


# ---- reading ---------------------------------------------------------------------------------
def _read_lines(data: bytes, compressed: bool) -> list[str]:
    text = (gzip.decompress(data) if compressed else data).decode("utf-8")
    return [line for line in text.split("\n") if line]


def read_manifest(archive: MatchArchive, match_id: str) -> dict[str, Any]:
    manifest: dict[str, Any] = json.loads(archive.get(match_id, MANIFEST))
    return manifest


def list_manifests(archive: MatchArchive) -> list[dict[str, Any]]:
    """Manifests of finished matches, newest first. A manifest that cannot be read is skipped."""
    out: list[dict[str, Any]] = []
    for match_id in archive.matches():
        try:
            out.append(read_manifest(archive, match_id))
        except (ArchiveMissing, json.JSONDecodeError):
            continue
    return sorted(out, key=lambda m: str(m["created_at"]), reverse=True)


def load_record(archive: MatchArchive, match_id: str) -> "MatchRecord":
    """A finished match from the archive. ArchiveMissing if it was never finished or never saved."""
    from .store import MatchRecord

    read_manifest(archive, match_id)  # no manifest, no match
    brief = MatchBrief.model_validate_json(archive.get(match_id, BRIEF))
    registry = FactRegistry()
    fact_lines = _read_lines(archive.get(match_id, FACTS), True)
    registry.aggregates = dict(json.loads(fact_lines[0])["aggregates"])
    for line in fact_lines[1:]:
        registry.add(Fact.model_validate_json(line))
    graph = ClaimGraph.model_validate_json(archive.get(match_id, CLAIM_GRAPH))
    claims: dict[str, list[Any]] = {}
    for c in graph.claims:
        claims.setdefault(c.beat_id.root, []).append(c)
    freeze = {}
    for line in _read_lines(archive.get(match_id, FREEZE), True):
        row = json.loads(line)
        freeze[row["event_id"]] = PositionFrame.model_validate(row["frame"])
    return MatchRecord(
        brief=brief,
        registry=registry,
        events=[
            Event.model_validate_json(line)
            for line in _read_lines(archive.get(match_id, EVENTS), True)
        ],
        freeze_frames=freeze,
        beats=[
            Beat.model_validate_json(line)
            for line in _read_lines(archive.get(match_id, BEATS), False)
        ],
        claims=claims,
        finished=True,
    )


def load_json(archive: MatchArchive, match_id: str, name: str) -> Any:
    """audit.json, producer_log.json or usage.json of a finished match."""
    read_manifest(archive, match_id)
    return json.loads(archive.get(match_id, name))


def load_frames(archive: MatchArchive, match_id: str) -> Iterator[PositionFrame]:
    """The 5 Hz frames of a finished match, for cached replays."""
    read_manifest(archive, match_id)
    for line in _read_lines(archive.get(match_id, FRAMES), True):
        yield PositionFrame.model_validate_json(line)
