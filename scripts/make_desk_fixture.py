"""Build apps/web/fixtures/desk.json for the static live desk.

Reads an archived match (brief, facts, beats, events, freeze frames, score). The archive of
m-red-card-flip-3 was saved with no claims, so the claims come from a captured SSE run of the same
match: the final text and verdict of each claim id are the last claim or verdict message for it.
The fact registry is rebuilt from the archived brief, events and frames with the current intel
(extract_all, then the beat detector for the on-demand facts), so running totals, momentum and
labels are the ones the engine makes now. Every claim's beat and every fact it cites must resolve in
the rebuilt registry, or the script exits 1.
"""

import argparse
import gzip
import json
import re
import sys
from pathlib import Path
from typing import Any

from contracts.models import Beat, Event, Fact, PositionFrame
from intel.beats import detect_all
from intel.desk import (
    BUCKET_COUNT,
    RUNNING_METRICS,
    attacking_actions,
    bucket_id,
    bucket_number,
    highlight_for,
    minute_mark,
)
from intel.engine import extract_all
from intel.labels import LabelContext, desk_label_for
from intel.registry import FactRegistry
from intel.score import is_goal, match_score
from intel.sources import aggregate_label, freeze_frame_label, window_label
from intel.windows import windows as window_table

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "apps" / "web" / "fixtures" / "desk.json"
MAX_BYTES = 400 * 1024
TICKER_LEN = 5
# Claim fields the desk shows; the checker, audit and span bookkeeping stay in the archive.
CLAIM_KEYS = (
    "id",
    "beat_id",
    "lang",
    "text",
    "draft_text",
    "fact_ids",
    "numbers",
    "verdict",
    "reason",
    "correction",
)
SSE_BLOCK = re.compile(r"event: (claim|verdict)\ndata: (.*)")

Json = dict[str, Any]


def read_jsonl(path: Path) -> list[Json]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def read_claims(sse_path: Path) -> dict[str, Json]:
    """Last claim or verdict message per claim id."""
    final: dict[str, Json] = {}
    for block in sse_path.read_text().split("\n\n"):
        match = SSE_BLOCK.search(block)
        if match:
            data = json.loads(match.group(2))["data"]
            final[data["id"]] = data
    return final


def cited_fact_ids(claim: Json) -> list[str]:
    ids = list(claim["fact_ids"])
    ids += [n["fact_id"] for n in claim.get("numbers", []) if n.get("fact_id")]
    return ids


def check_resolves(
    claims: dict[str, Json], beat_ids: set[str], fact_ids: set[str]
) -> int:
    """Print the counts; return the number of unresolved references."""
    refs = [(c["id"], f) for c in claims.values() for f in cited_fact_ids(c)]
    missing_beats = sorted(
        c["id"] for c in claims.values() if c["beat_id"] not in beat_ids
    )
    missing_facts = sorted({(cid, fid) for cid, fid in refs if fid not in fact_ids})
    print(
        f"claims {len(claims)}, fact refs {len(refs)}, archive beats {len(beat_ids)}, rebuilt facts {len(fact_ids)}"
    )
    print(f"unresolved beats {missing_beats}, unresolved facts {missing_facts}")
    return len(missing_beats) + len(missing_facts)


def score_timeline(events: list[Event], by_name: dict[str, Fact]) -> list[Json]:
    """One entry per goal: the score after it (intel.score.match_score) and its score_after fact."""
    rows: list[Json] = []
    for event in sorted(events, key=lambda e: e.t.root):
        if not is_goal(event):
            continue
        home, away = match_score(events, event.t.root)
        fact = by_name[f"score_after({event.id.root})"]
        rows.append(
            {"t": event.t.root, "home": home, "away": away, "fact_id": fact.id.root}
        )
    return rows


def count_timeline(
    events: list[Json], facts: list[Json], last_minute: int
) -> list[Json]:
    """Events and facts available by the end of each match minute."""
    event_times = sorted(e["t"] for e in events)
    fact_times = sorted(f.get("scope", {}).get("t_to", 0.0) for f in facts)
    rows: list[Json] = []
    for minute in range(last_minute + 1):
        limit = minute * 60.0
        rows.append(
            {
                "minute": minute,
                "events": sum(1 for t in event_times if t <= limit),
                "facts": sum(1 for t in fact_times if t <= limit),
            }
        )
    return rows


def running_totals(by_name: dict[str, Fact]) -> list[Json]:
    """One entry per 5-minute mark: the match-to-date fact id of every metric for both sides."""
    rows: list[Json] = []
    for number in range(1, BUCKET_COUNT + 1):
        entry: Json = {"minute": minute_mark(number), "facts": {}}
        for metric in RUNNING_METRICS:
            for side in ("home", "away"):
                fact = by_name.get(f"{metric}({side}, to {minute_mark(number)}′)")
                if fact is None:
                    continue
                entry["facts"].setdefault(metric, {})[side] = fact.id.root
                if fact.scope is not None and fact.scope.t_to is not None:
                    entry["t_to"] = fact.scope.t_to.root
        rows.append(entry)
    return rows


def momentum_ids(by_name: dict[str, Fact]) -> list[str]:
    """The momentum(min-NN) fact ids in bucket order."""
    return [
        by_name[f"momentum({bucket_id(n)})"].id.root for n in range(1, BUCKET_COUNT + 1)
    ]


def rebuild_registry(
    archive: Path, brief: Json, events: list[Event]
) -> tuple[FactRegistry, LabelContext]:
    """The match's registry with the current intel, and the context its labels are written from."""
    frames = [
        PositionFrame.model_validate(r) for r in read_jsonl(archive / "frames.jsonl.gz")
    ]
    freeze = [
        PositionFrame.model_validate(r["frame"])
        for r in read_jsonl(archive / "freeze.jsonl.gz")
    ]
    teams = {"home": brief["home"]["name"], "away": brief["away"]["name"]}
    roster = {
        p["id"]: p["name"] for side in ("home", "away") for p in brief[side]["players"]
    }
    registry = extract_all(events, frames, freeze, roster, teams)
    detect_all(events, frames, freeze, registry)
    return registry, LabelContext(teams, {e.id.root: e for e in events}, registry)


def print_momentum(events: list[Event], by_name: dict[str, Fact]) -> None:
    """Every bucket's home and away attacking actions beside the momentum fact made from them."""
    buckets: dict[int, list[Event]] = {n: [] for n in range(1, BUCKET_COUNT + 1)}
    for e in events:
        buckets[bucket_number(e.period.value, e.t.root)].append(e)
    print("bucket  home  away  momentum (pp)")
    for number in range(1, BUCKET_COUNT + 1):
        fact = by_name[f"momentum({bucket_id(number)})"]
        home = attacking_actions(buckets[number], "home")
        away = attacking_actions(buckets[number], "away")
        print(f"{bucket_id(number)}  {home:4d}  {away:4d}  {float(fact.value):+.0f}")


def fact_row(fact: Fact, ctx: LabelContext) -> Json:
    row: Json = json.loads(fact.model_dump_json(by_alias=True, exclude_none=True))
    row["label"] = desk_label_for(fact, ctx)
    return row


def build(archive: Path, sse: Path, snapshot_minute: int) -> Json:
    manifest = json.loads((archive / "manifest.json").read_text())
    brief = json.loads((archive / "brief.json").read_text())
    graph = json.loads((archive / "claim_graph.json").read_text())
    beats = read_jsonl(archive / "beats.jsonl")
    event_rows = read_jsonl(archive / "events.jsonl.gz")
    events = {e["id"]: e for e in event_rows}
    registry, ctx = rebuild_registry(
        archive, brief, [Event.model_validate(e) for e in event_rows]
    )
    aggregates = registry.aggregates
    fact_models = {f.id.root: f for f in registry.all()}
    facts = {fid: fact_row(f, ctx) for fid, f in fact_models.items()}
    archived = {f["id"] for f in read_jsonl(archive / "facts.jsonl.gz")[1:]}
    print(
        f"rebuilt facts {len(facts)}, archived {len(archived)}, "
        f"in the archive but not rebuilt {len(archived - set(facts))}"
    )
    frames = {
        row["event_id"]: row["frame"] for row in read_jsonl(archive / "freeze.jsonl.gz")
    }

    claims = read_claims(sse)
    if check_resolves(claims, {b["id"] for b in beats}, set(facts)):
        raise SystemExit(1)

    claim_rows = [
        {k: c[k] for k in CLAIM_KEYS if k in c}
        for c in sorted(claims.values(), key=lambda c: c["id"])
    ]
    feed_beats = sorted(
        (b for b in beats if any(c["beat_id"] == b["id"] for c in claim_rows)),
        key=lambda b: b["t_detect"],
    )
    by_name = {f.name: f for f in fact_models.values()}
    print_momentum([Event.model_validate(e) for e in event_rows], by_name)
    running = running_totals(by_name)
    momentum = momentum_ids(by_name)
    desk_ids = {
        fid for r in running for sides in r["facts"].values() for fid in sides.values()
    } | set(momentum)
    event_models = [Event.model_validate(e) for e in event_rows]
    score_rows = score_timeline(event_models, by_name)
    keep_facts = (
        {fid for c in claim_rows for fid in cited_fact_ids(c)}
        | desk_ids
        | {r["fact_id"] for r in score_rows}
    )

    snapshot_t = snapshot_minute * 60.0
    ticker = [
        e["id"]
        for e in sorted(events.values(), key=lambda e: e["t"])
        if e["t"] <= snapshot_t
    ][-TICKER_LEN:]
    source_ids = {s for fid in keep_facts for s in facts[fid]["source_ids"]}
    keep_events = (
        {s for s in source_ids if s in events}
        | set(ticker)
        | {b["anchor_event_id"] for b in feed_beats}
    )
    windows_by_id = {
        w.id: w for w in window_table(Event.model_validate(e) for e in event_rows)
    }
    other_sources: Json = {}
    for source in sorted(source_ids - set(events)):
        if source in aggregates:
            other_sources[source] = {
                "kind": "aggregate",
                "description": aggregates[source],
                "label": aggregate_label(source, ctx),
            }
        elif source in windows_by_id:
            other_sources[source] = {
                "kind": "window",
                "t_from": windows_by_id[source].t_from,
                "t_to": windows_by_id[source].t_to,
                "label": window_label(
                    windows_by_id[source].t_from, windows_by_id[source].t_to
                ),
            }
        elif source.startswith("ff-"):
            other_sources[source] = {
                "kind": "freeze_frame",
                "event_id": f"ev-{source[3:]}",
                "label": freeze_frame_label(f"ev-{source[3:]}", ctx),
            }
        else:
            print(
                f"source {source} is not an event, window, aggregate or freeze frame",
                file=sys.stderr,
            )
            raise SystemExit(1)

    players = {
        p["id"]: {"name": p["name"], "number": p["number"]}
        for side in ("home", "away")
        for p in brief[side]["players"]
    }
    return {
        "match_id": manifest["match_id"],
        "provenance": {
            "archive": f"data/archive/{manifest['match_id']}",
            "claims": "captured SSE run of the same match; the archive was saved with no claims",
        },
        "brief": brief,
        "final_score": graph["final_score"],
        "snapshot": {"minute": snapshot_minute, "t": snapshot_t},
        "players": players,
        "beats": feed_beats,
        "claims": claim_rows,
        "facts": [facts[fid] for fid in sorted(keep_facts)],
        "events": [events[eid] for eid in sorted(keep_events)],
        "sources": other_sources,
        "frames": {
            b["anchor_event_id"]: frames[b["anchor_event_id"]] for b in feed_beats
        },
        "highlights": {
            b["id"]: json.loads(h.model_dump_json(exclude_none=True))
            for b in feed_beats
            if (
                h := highlight_for(
                    Beat.model_validate(b),
                    next(
                        (e for e in event_models if e.id.root == b["anchor_event_id"]),
                        None,
                    ),
                )
            )
        },
        "ticker_event_ids": ticker,
        "score_timeline": score_rows,
        "count_timeline": count_timeline(
            list(events.values()), list(facts.values()), 96
        ),
        "running": running,
        "momentum": momentum,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--archive", type=Path, default=ROOT / "data" / "archive" / "m-red-card-flip-3"
    )
    parser.add_argument("--claims-sse", type=Path, default=ROOT / "match.sse")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--snapshot-minute", type=int, default=71)
    args = parser.parse_args()

    fixture = build(args.archive, args.claims_sse, args.snapshot_minute)
    verdicts: dict[str, int] = {}
    for claim in fixture["claims"]:
        verdicts[claim["verdict"]] = verdicts.get(claim["verdict"], 0) + 1
    missing = {"verified", "rephrased", "blocked"} - set(verdicts)
    if missing:
        print(f"missing verdicts: {sorted(missing)}", file=sys.stderr)
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(fixture, separators=(",", ":"), ensure_ascii=False)
    args.out.write_text(text + "\n")
    size = len(text.encode())
    print(f"match ids: {fixture['match_id']} (claims from {args.claims_sse.name})")
    print(f"verdict counts: {verdicts}")
    print(f"fixture: {args.out.relative_to(ROOT)}, {size} bytes")
    if size > MAX_BYTES:
        print(f"fixture is over {MAX_BYTES} bytes", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
