"""Narrator Trials results to the file the web pages draw. No model calls.

The browser draws JSON and never computes (seam rule 3), so ranks, worst moments, picks, clocks and
the facts behind each moment are all worked out here. Each fixture's match is rebuilt from the pack
(generation is deterministic and cached), never re-played.

uv run python -m evals.trials_web evals/reports/trials/pack-v1.json    # writes web-pack-v1.json
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import yaml
from agents.llm_client import load_models
from agents.pipeline import tool_result
from contracts.models import Beat, Event, TrialsWeb
from intel.display import render_minute
from mcp_match import InMemoryMatchStore, build_server

from .golden import build_store_from_brief
from .run import ROOT
from .trials import PACK_PATH, Fixture, load_pack

NEXT_UP_PATH = Path(__file__).parent / "trials" / "next_up.yaml"
WEB_FIXTURES_DIR = ROOT / "apps" / "web" / "fixtures" / "trials"
MAX_HELD_SHARE = (
    0.10  # a candidate with more beats unanswered than this is not measured
)
NOTE_CHARS = 110
MAX_SOURCES = 6
SIZE_LIMIT = 1_500_000
# Lowest first: what the worst moment is picked from.
VERDICT_ORDER = {"OVERTURNED": 0, "AMENDED": 1, "HELD": 2, "STANDS": 3}

Json = dict[str, Any]


def is_measured(row: Json) -> bool:
    """held / claims <= 0.10. A run the model mostly did not answer is not a result."""
    return bool(row["claims"] > 0 and row["held"] / row["claims"] <= MAX_HELD_SHARE)


def ranks_of(summary: list[Json]) -> tuple[Json, list[str]]:
    """1-based ranks of the measured rows in summary order, and the Table order: measured rows by
    rank, then the unmeasured ones (no rank)."""
    measured = [r["candidate"] for r in summary if is_measured(r)]
    unmeasured = [r["candidate"] for r in summary if not is_measured(r)]
    return {c: i for i, c in enumerate(measured, 1)}, [*measured, *unmeasured]


def trim(text: str, limit: int = NOTE_CHARS) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def worst_of(claims: list[Json], candidate: str) -> Json | None:
    """The candidate's lowest scored verdict (OVERTURNED < AMENDED < HELD < STANDS); on a tie, the
    latest beat. `note` is one short line."""
    rows = [c for c in claims if c["candidate"] == candidate and c["scored"]]
    if not rows:
        return None
    low = min(VERDICT_ORDER[c["verdict"]] for c in rows)
    pick = max(
        (c for c in rows if VERDICT_ORDER[c["verdict"]] == low),
        key=lambda c: (c["minute"], c["beat"]),
    )
    if pick["verdict"] == "AMENDED" and pick["failed_span"] and pick["corrected_span"]:
        note = f"{pick['failed_span']} → {pick['corrected_span']}"
    elif pick["reasons"]:
        note = pick["reasons"][0]
    else:
        note = pick["text"]
    return {
        "fixture": pick["fixture"],
        "beat": pick["beat"],
        "verdict": pick["verdict"],
        "note": trim(note),
    }


def picks_of(summary: list[Json]) -> Json:
    """The cards under the table, from measured rows only. Each is null when nothing qualifies."""
    measured = [r for r in summary if is_measured(r)]
    cleared = [r for r in measured if r["cleared"]]
    priced = [r for r in cleared if not isinstance(r["usd_per_match"], str)]
    live = min(cleared, key=lambda r: r["p90_ms"], default=None)
    budget = min(priced, key=lambda r: r["usd_per_match"], default=None)
    uncleared = [r["candidate"] for r in measured if not r["cleared"]]
    return {
        "live_feed": (
            {"candidate": live["candidate"], "p90_ms": live["p90_ms"]} if live else None
        ),
        "budget": (
            {"candidate": budget["candidate"], "usd_per_match": budget["usd_per_match"]}
            if budget
            else None
        ),
        "not_cleared": uncleared or None,
    }


def live_narrator_of(candidates: list[Json], deployment: str) -> str | None:
    """The candidate whose deployment is the one the API narrates with live."""
    return next((c["id"] for c in candidates if c["deployment"] == deployment), None)


def clock_at(events: list[Event], t: float) -> str:
    """The broadcast clock at match time `t`, with the period of the last event at or before it."""
    before = [e for e in events if e.t.root <= t]
    period = int((before[-1] if before else events[0]).period.value)
    return render_minute(t, "en", period)[0]


def trap_beats(fixture: Fixture, beats: list[Beat]) -> list[Json]:
    """The beat each trap sits on: the planted beat, whose anchor is the trap's event."""
    by_planted = {b.planted_beat_id: b for b in beats if b.planted_beat_id}
    rows = []
    for trap in fixture.traps:
        beat = by_planted[f"pb-{int(trap['planted']):02d}"]
        rows.append({"beat": beat.id.root, "event_id": beat.anchor_event_id.root})
    return rows


async def bundles_of(
    store: InMemoryMatchStore, match_id: str, beat_ids: list[str]
) -> dict[str, Json]:
    """The bundle the Narrator read for each beat, through the same tool."""
    server = build_server(store, writable=False)
    return {
        beat_id: tool_result(
            await server.call_tool(
                "get_beat_bundle", {"match_id": match_id, "beat_id": beat_id}
            )
        )
        for beat_id in beat_ids
    }


def moment_of(
    store: InMemoryMatchStore,
    match_id: str,
    beat: Beat,
    bundle: Json,
    events: list[Event],
) -> Json:
    """One beat as the Compare page draws it."""
    brief = store.brief(match_id)
    roster = {p.id.root: p.name for t in (brief.home, brief.away) for p in t.players}
    by_id = {e.id.root: e for e in events}
    anchor = beat.anchor_event_id.root
    ids = [anchor] if anchor in by_id else []
    for fact in bundle["facts"]:
        for s in fact["source_ids"]:
            if s in by_id and s not in ids:
                ids.append(s)
    sources = []
    for eid in ids[:MAX_SOURCES]:
        e = by_id[eid]
        sources.append(
            {
                "id": eid,
                "type": e.type.value,
                "player": roster.get(e.player_id.root) if e.player_id else None,
                "clock": render_minute(e.t.root, "en", int(e.period.value))[0],
            }
        )
    frame = store.freeze_frame(match_id, anchor)
    return {
        "kind": beat.kind.value,
        "label": beat.label,
        "clock": clock_at(events, beat.t_detect.root),
        "t": beat.t_detect.root,
        "facts": [
            {"id": f["id"], "label": f["label"], "text": f["display"]["en"][0]}
            for f in bundle["facts"]
        ],
        "sources": sources,
        "freeze": (
            frame.model_dump(mode="json", by_alias=True, exclude_none=True)
            if frame
            else None
        ),
    }


def build_web(
    results: Json,
    fixtures: list[Fixture],
    narrator_deployment: str,
    next_up: list[Json],
) -> Json:
    """Everything the Table and Compare pages draw, from a results file and the pack."""
    summary = results["summary"]
    ranks, order = ranks_of(summary)
    measured = {r["candidate"]: is_measured(r) for r in summary}
    worst = {
        r["candidate"]: worst_of(results["claims"], r["candidate"])
        if measured[r["candidate"]]
        else None
        for r in summary
    }
    wanted: dict[str, set[str]] = {}
    for c in results["claims"]:
        wanted.setdefault(c["fixture"], set()).add(c["beat"])

    meta = {f["id"]: f for f in results["fixtures"]}
    fixture_rows: list[Json] = []
    moments: Json = {}
    clocks: dict[tuple[str, str], str] = {}
    for fixture in fixtures:
        if fixture.id not in meta:
            continue
        store, match_id = build_store_from_brief(fixture.make_brief())
        if match_id != meta[fixture.id]["match_id"]:
            raise SystemExit(
                f"{fixture.id}: the pack builds {match_id}, not the results' match"
            )
        events = sorted(store.events(match_id), key=lambda e: (e.t.root, e.seq))
        beats = {b.id.root: b for b in store.beats(match_id)}
        fixture_rows.append(
            {
                **meta[fixture.id],
                "match_brief": json.loads(
                    fixture.make_brief().model_dump_json(
                        by_alias=True, exclude_none=True
                    )
                ),
                "trap_beats": trap_beats(fixture, list(beats.values())),
            }
        )
        moments[fixture.id] = {}
        beat_ids = sorted(
            wanted.get(fixture.id, ()), key=lambda b: beats[b].t_detect.root
        )
        bundles = asyncio.run(bundles_of(store, match_id, beat_ids))
        for beat_id in beat_ids:
            m = moment_of(store, match_id, beats[beat_id], bundles[beat_id], events)
            moments[fixture.id][beat_id] = m
            clocks[(fixture.id, beat_id)] = m["clock"]

    web: Json = {
        "pack": results["pack"],
        "results": results,
        "ranks": ranks,
        "order": order,
        "measured": measured,
        "worst": worst,
        "picks": picks_of(summary),
        "live_narrator": live_narrator_of(results["candidates"], narrator_deployment),
        "fixtures": fixture_rows,
        "moments": moments,
        "claim_clock": {
            str(i): clocks[(c["fixture"], c["beat"])]
            for i, c in enumerate(results["claims"])
        },
        "next_up": next_up,
    }
    return web


def shrink_to_limit(web: Json, limit: int = SIZE_LIMIT) -> list[str]:
    """If the file is over `limit` bytes, drop `freeze` from the beats that are neither a trap beat
    nor any candidate's worst moment. Returns what was dropped, for the log."""
    if len(json.dumps(web, ensure_ascii=False).encode()) <= limit:
        return []
    keep = {(f["id"], t["beat"]) for f in web["fixtures"] for t in f["trap_beats"]} | {
        (w["fixture"], w["beat"]) for w in web["worst"].values() if w
    }
    dropped = []
    for fid, beats in web["moments"].items():
        for bid, m in beats.items():
            if (fid, bid) not in keep and m["freeze"] is not None:
                m["freeze"] = None
                dropped.append(f"{fid}/{bid}")
    return dropped


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("results", type=Path, help="a trials results JSON")
    args = parser.parse_args()
    results: Json = json.loads(args.results.read_text("utf-8"))
    pack, fixtures = load_pack(PACK_PATH)
    if pack != results["pack"]:
        raise SystemExit(f"the results are for {results['pack']}, the pack is {pack}")
    narrator = str(load_models()["narrator"]["deployment"])
    next_up = yaml.safe_load(NEXT_UP_PATH.read_text("utf-8")) or []
    web = build_web(results, fixtures, narrator, next_up)
    dropped = shrink_to_limit(web)
    if dropped:
        print(f"over {SIZE_LIMIT} bytes: dropped freeze frames of {len(dropped)} beats")
    TrialsWeb.model_validate(web)  # the contract, before anything is written
    stem = args.results.stem  # pack-v1 or pack-v1-smoke
    WEB_FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    out = WEB_FIXTURES_DIR / f"web-{stem}.json"
    out.write_text(json.dumps(web, indent=1, ensure_ascii=False) + "\n", "utf-8")
    print(f"{out} {out.stat().st_size} bytes", file=sys.stdout)


if __name__ == "__main__":
    main()
