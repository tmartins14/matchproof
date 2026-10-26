"""Realism report: events hash and realism measures for the six pack fixtures and calibration seeds 1-8.

uv run python -m scripts.realism_report --out docs/realism/baseline.json
"""

import argparse
import hashlib
import json
from collections.abc import Iterator
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

from contracts.models import Event
from sim import iter_events
from sim.brief import STORYLINES, make_brief
from sim.positions import run
from sim.realism import MAX_ACCEL_MS2, MAX_SPEED_MS, Report

from evals.trials import load_pack

SEEDS = range(1, 9)


def jobs() -> list[tuple[str, str, int]]:
    """(label, storyline, seed) for each pack fixture, then each calibration storyline and seed."""
    out: list[tuple[str, str, int]] = []
    _, fixtures = load_pack()
    for f in fixtures:
        out.append((f.id, f.storyline, f.seed))
    for story in sorted(STORYLINES):
        for seed in SEEDS:
            out.append((f"cal-{story}-{seed}", story, seed))
    return out


def one(job: tuple[str, str, int]) -> dict[str, Any]:
    label, story, seed = job
    if label.startswith("fx-"):
        brief = next(f for f in load_pack()[1] if f.id == label).make_brief()
    else:
        brief = make_brief(storyline_id=story, seed=seed)
    h = hashlib.sha256()
    rep = Report()

    def hashed() -> Iterator[Event]:
        for e in iter_events(brief):
            h.update(e.model_dump_json(by_alias=True, exclude_none=True).encode())
            h.update(b"\n")
            yield e

    for kind, event, frame in run(brief, hashed()):
        rep.feed(kind, event, frame)
    return {"label": label, "events_sha256": h.hexdigest(), **rep.summary()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=2)
    a = ap.parse_args()
    with ProcessPoolExecutor(a.workers) as ex:
        matches = list(ex.map(one, jobs()))
    fwd = sum(m["forward_passes"] for m in matches)
    off = sum(m["offside_passes"] for m in matches)
    agg = {
        "offside_share": off / fwd if fwd else 0.0,
        "forward_passes": fwd,
        "snap_jumps": sum(m["snap_jumps"] for m in matches),
        "steps": sum(m["steps"] for m in matches),
        "max_speed": max(m["max_speed"] for m in matches),
        "max_accel": max(m["max_accel"] for m in matches),
        "teammate_overlap": sum(m["teammate_overlap"] for m in matches) / len(matches),
        "line_coherence": sum(m["line_coherence"] for m in matches) / len(matches),
    }
    doc = {
        "caps": {"speed_ms": MAX_SPEED_MS, "accel_ms2": MAX_ACCEL_MS2},
        "aggregate": agg,
        "matches": matches,
    }
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(agg, indent=2))


if __name__ == "__main__":
    main()
