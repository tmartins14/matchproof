"""Recorded fixture streams: deterministic, ordered in time, and carrying the web export's beats."""

import asyncio
import gzip
import json
from pathlib import Path
from typing import Any

import pytest

from evals.trials import PACK_PATH, load_pack
from scripts.record_fixtures import DEFAULT_DIR, VirtualPacer, record
from scripts.record_stream import MAX_GZ_BYTES

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "apps" / "web" / "fixtures" / "trials" / "web-pack-v1.json"
FIXTURE_IDS = [f.id for f in load_pack(PACK_PATH)[1]]


def lines_of(fixture: str) -> list[dict[str, Any]]:
    packed = (DEFAULT_DIR / f"{fixture}.ndjson.gz").read_bytes()
    return [json.loads(line) for line in gzip.decompress(packed).splitlines()]


def test_virtual_pacer_jumps_forward_and_never_back() -> None:
    async def run() -> float:
        pacer = VirtualPacer()
        await pacer.sleep_until(2.5)
        await pacer.sleep_until(1.0)
        return pacer.now()

    assert asyncio.run(run()) == 2.5


def test_recording_twice_gives_the_same_bytes_as_the_committed_file() -> None:
    fixture = next(f for f in load_pack(PACK_PATH)[1] if f.id == "fx-04")
    first, _, _ = record(fixture)
    second, _, _ = record(fixture)
    assert first == second
    assert first == (DEFAULT_DIR / "fx-04.ndjson.gz").read_bytes()


@pytest.mark.parametrize("fixture", FIXTURE_IDS)
def test_wall_ms_never_decreases_and_the_file_is_under_the_cap(fixture: str) -> None:
    rows = lines_of(fixture)
    walls = [r["wall_ms"] for r in rows]
    assert walls[0] == 0
    assert walls == sorted(walls)
    assert len((DEFAULT_DIR / f"{fixture}.ndjson.gz").read_bytes()) <= MAX_GZ_BYTES


@pytest.mark.parametrize("fixture", FIXTURE_IDS)
def test_recorded_beats_are_the_web_exports_moments(fixture: str) -> None:
    recorded = {
        r["msg"]["data"]["id"] for r in lines_of(fixture) if r["msg"]["type"] == "beat"
    }
    moments = set(json.loads(WEB.read_text("utf-8"))["moments"][fixture])
    assert recorded == moments
