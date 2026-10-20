"""CLI: uv run python -m sim generate --story late_comeback --seed 7 --out data/matches/<id>.jsonl"""

import argparse
from collections import Counter
from pathlib import Path

from contracts.models import Event, MatchBrief

from . import generate
from .brief import DEFAULT_AWAY, DEFAULT_HOME, STORYLINES, TeamTactics, make_brief
from .calibrate import (
    collect,
    evaluate,
    format_table,
    load_targets,
    parse_seeds,
    report_json,
)
from .tactics import FORMATIONS


def summarize(brief: MatchBrief, events: list[Event]) -> str:
    """Plain summary table. Possession share follows Opta: a side's completed passes over both sides'."""
    rows: dict[str, dict[str, float]] = {s: Counter() for s in ("home", "away")}  # type: ignore[misc]
    for e in events:
        r = rows[e.side.value]
        t = e.type.value
        if t == "pass":
            r["passes"] += 1
            r["complete"] += e.outcome is not None and e.outcome.value == "complete"
        elif t == "shot" and e.shot is not None:
            r["shots"] += 1
            r["xg"] += e.shot.xg
            r["goals"] += e.outcome is not None and e.outcome.value == "goal"
    total_complete = rows["home"]["complete"] + rows["away"]["complete"]
    hit = sorted({e.planted_beat_id for e in events if e.planted_beat_id})
    lines = [
        f"{brief.match_id}: {len(events)} events",
        f"{'':14}{brief.home.short:>8}{brief.away.short:>8}",
    ]
    for label, key in (("passes", "passes"), ("shots", "shots"), ("goals", "goals")):
        lines.append(
            f"{label:14}{int(rows['home'][key]):>8}{int(rows['away'][key]):>8}"
        )
    comp = [
        100 * rows[s]["complete"] / max(rows[s]["passes"], 1) for s in ("home", "away")
    ]
    lines.append(f"{'pass completion':14}{comp[0]:>7.0f}%{comp[1]:>7.0f}%")
    lines.append(f"{'xG':14}{rows['home']['xg']:>8.2f}{rows['away']['xg']:>8.2f}")
    share = [
        100 * rows[s]["complete"] / max(total_complete, 1) for s in ("home", "away")
    ]
    lines.append(f"{'possession':14}{share[0]:>7.0f}%{share[1]:>7.0f}%")
    lines.append(
        f"final score: {int(rows['home']['goals'])}-{int(rows['away']['goals'])}"
    )
    lines.append(f"planted beats hit: {len(hit)} of {len(brief.planted_beats)}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="sim")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("calibrate")
    c.add_argument("--seeds", default="1-8")
    c.add_argument("--out", type=Path)
    c.add_argument("--git-sha", default="unknown")
    g = sub.add_parser("generate")
    g.add_argument("--story", required=True, choices=sorted(STORYLINES))
    g.add_argument("--seed", type=int, default=0)
    g.add_argument("--out", type=Path)
    for side in ("home", "away"):
        g.add_argument(f"--{side}-formation", choices=sorted(FORMATIONS))
        for dial in ("press", "directness", "line-height"):
            g.add_argument(f"--{side}-{dial}", type=float)
    a = ap.parse_args(argv)
    if a.cmd == "calibrate":
        seeds = parse_seeds(a.seeds)
        rows = evaluate(collect(seeds), load_targets())
        print(format_table(rows))
        if a.out:
            a.out.parent.mkdir(parents=True, exist_ok=True)
            a.out.write_text(report_json(rows, seeds, a.git_sha), encoding="utf-8")
        return 0 if all(r.ok for r in rows) else 1

    def tactics(base: TeamTactics, side: str) -> TeamTactics:
        def pick(name: str, current: object) -> object:
            v = getattr(a, f"{side}_{name}")
            return current if v is None else v

        return TeamTactics(
            base.name,
            base.short,
            str(pick("formation", base.formation)),
            float(pick("press", base.press)),  # type: ignore[arg-type]
            float(pick("directness", base.directness)),  # type: ignore[arg-type]
            float(pick("line_height", base.line_height)),  # type: ignore[arg-type]
        )

    brief = make_brief(
        tactics(DEFAULT_HOME, "home"), tactics(DEFAULT_AWAY, "away"), a.story, a.seed
    )
    events = generate(brief)
    out = a.out or Path("data/matches") / f"{brief.match_id}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for e in events:
            f.write(e.model_dump_json(by_alias=True, exclude_none=True) + "\n")
    out.with_suffix(".brief.json").write_text(
        brief.model_dump_json(by_alias=True, exclude_none=True, indent=2),
        encoding="utf-8",
    )
    print(summarize(brief, events))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
