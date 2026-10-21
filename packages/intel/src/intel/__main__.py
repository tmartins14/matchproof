"""CLI: uv run python -m intel facts|beats --match data/matches/<match_id>"""

import argparse
import gc
import json
from collections import Counter
from pathlib import Path

from contracts.models import Beat, Event, Fact, PositionFrame

from .beats import detect_all
from .engine import extract_all
from .registry import FactRegistry


def load_match(
    base: Path,
) -> tuple[list[Event], list[PositionFrame], list[PositionFrame]]:
    """Events, 5 Hz frames and freeze frames written by `python -m sim generate`."""

    def lines(suffix: str) -> list[str]:
        path = base.with_name(base.name + suffix)
        return path.read_text(encoding="utf-8").splitlines()

    events = [Event.model_validate_json(x) for x in lines(".jsonl")]
    frames = [PositionFrame.model_validate_json(x) for x in lines(".frames.jsonl")]
    freeze = [PositionFrame.model_validate_json(x) for x in lines(".freeze.jsonl")]
    return events, frames, freeze


def load_roster(base: Path) -> dict[str, str]:
    """Player id to name from <match_id>.brief.json."""
    brief = json.loads(base.with_name(base.name + ".brief.json").read_text("utf-8"))
    return {
        p["id"]: p["name"] for side in ("home", "away") for p in brief[side]["players"]
    }


def write_facts(base: Path, registry: FactRegistry) -> tuple[Path, list[Fact]]:
    facts = registry.all()
    out = base.with_name(base.name + ".facts.jsonl")
    with out.open("w", encoding="utf-8") as fh:
        for fact in facts:
            fh.write(fact.model_dump_json(by_alias=True, exclude_none=True) + "\n")
    return out, facts


def print_beats(base: Path, beats: list[Beat], registry: FactRegistry) -> int:
    out = base.with_name(base.name + ".beats.jsonl")
    with out.open("w", encoding="utf-8") as fh:
        for beat in beats:
            fh.write(beat.model_dump_json(by_alias=True, exclude_none=True) + "\n")
    # The registry now holds the on-demand since() and last-minutes facts the beats cite, so this
    # file has every fact in beats.jsonl; the cached replay follows the chain from beats to facts.
    facts_out, facts = write_facts(base, registry)
    print(
        f"{base.name}: {len(beats)} beats -> {out}; {len(facts)} facts -> {facts_out}"
    )
    for beat in beats:
        print(
            f"  {beat.label:>11}  {beat.kind.value:21}{beat.origin.value:9}"
            f"salience={beat.salience:.2f}  facts={len(beat.fact_ids)}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="intel")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("facts")
    f.add_argument("--match", type=Path, required=True)
    f.add_argument("--samples", type=int, default=10)
    b = sub.add_parser("beats")
    b.add_argument("--match", type=Path, required=True)
    a = ap.parse_args(argv)
    base: Path = a.match
    gc.disable()  # tens of thousands of frame models; the cyclic collector would crawl over them
    events, frames, freeze = load_match(base)
    registry = extract_all(events, frames, freeze, load_roster(base))
    if a.cmd == "beats":
        return print_beats(base, detect_all(events, frames, freeze, registry), registry)
    out, facts = write_facts(base, registry)
    counts = Counter(x.extractor.name for x in facts)
    print(f"{base.name}: {len(facts)} facts -> {out}")
    for name, n in sorted(counts.items()):
        print(f"  {name:24}{n:>7}")
    step = max(len(facts) // a.samples, 1)
    for fact in facts[::step][: a.samples]:
        scope = fact.scope.side.value if fact.scope and fact.scope.side else "-"
        print(
            f"  {fact.name}  [{scope}]  value={fact.value}  en={fact.display.en}  "
            f"sources={[s.root for s in fact.source_ids][:4]}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
