"""Calibration report: run every storyline on each seed with default tactics and compare to bands."""

import json
from dataclasses import dataclass
from pathlib import Path
from statistics import mean

import yaml
from contracts.models import Event

from . import generate
from .brief import STORYLINES, make_brief

TARGETS_PATH = Path(__file__).resolve().parents[2] / "calibration" / "targets.yaml"
# A single run may sit outside the band by at most this share of the band width.
RUN_TOLERANCE = 0.15


@dataclass(frozen=True)
class Target:
    id: str
    per: str
    band: tuple[float, float]
    unit: str
    source: str
    status: str


@dataclass(frozen=True)
class Row:
    target: Target
    mean: float
    low: float
    high: float
    ok: bool


def load_targets(path: Path | None = None) -> list[Target]:
    raw = yaml.safe_load((path or TARGETS_PATH).read_text(encoding="utf-8"))
    return [
        Target(
            r["id"],
            r["per"],
            (float(r["band"][0]), float(r["band"][1])),
            r["unit"],
            r["source"],
            r["status"],
        )
        for r in raw
    ]


def parse_seeds(spec: str) -> list[int]:
    """'1-8' or '1,3,5' into a list of seeds."""
    seeds: list[int] = []
    for part in spec.split(","):
        lo, _, hi = part.partition("-")
        seeds.extend(range(int(lo), int(hi or lo) + 1))
    return seeds


def match_metrics(events: list[Event]) -> dict[str, list[float]]:
    """Every calibration metric for one match: two values for team metrics, one for match metrics."""
    out: dict[str, list[float]] = {}

    def add(key: str, value: float) -> None:
        out.setdefault(key, []).append(value)

    complete = {s: 0 for s in ("home", "away")}
    for e in events:
        if (
            e.type.value == "pass"
            and e.outcome is not None
            and e.outcome.value == "complete"
        ):
            complete[e.side.value] += 1
    total_complete = max(sum(complete.values()), 1)
    match_xg = 0.0
    for side in ("home", "away"):
        mine = [e for e in events if e.side.value == side]
        passes = [e for e in mine if e.type.value == "pass" and e.pass_ is not None]
        shots = [e for e in mine if e.type.value == "shot" and e.shot is not None]
        xg = sum(e.shot.xg for e in shots if e.shot)
        match_xg += xg
        add("passes", len(passes))
        add("pass_completion", complete[side] / max(len(passes), 1))
        add(
            "mean_pass_length", mean(e.pass_.length_m or 0.0 for e in passes if e.pass_)
        )
        add(
            "progressive_pass_share",
            sum(1 for e in passes if e.pass_ and e.pass_.progressive)
            / max(len(passes), 1),
        )
        add("shots", len(shots))
        add("xg_per_team", xg)
        add("xg_per_shot", xg / max(len(shots), 1))
        add("possession_share", complete[side] / total_complete)
        add("fouls", sum(1 for e in mine if e.type.value == "foul"))
        add(
            "yellow_cards",
            sum(
                1
                for e in mine
                if e.type.value == "card"
                and e.outcome is not None
                and e.outcome.value == "yellow"
            ),
        )
        add("corners", sum(1 for e in mine if e.type.value == "corner"))
    add("xg_per_match", match_xg)
    return out


def collect(seeds: list[int]) -> dict[str, list[float]]:
    values: dict[str, list[float]] = {}
    for story in sorted(STORYLINES):
        for seed in seeds:
            for key, vs in match_metrics(
                generate(make_brief(storyline_id=story, seed=seed))
            ).items():
                values.setdefault(key, []).extend(vs)
    return values


def evaluate(values: dict[str, list[float]], targets: list[Target]) -> list[Row]:
    rows: list[Row] = []
    for t in targets:
        vs = values[t.id]
        lo, hi = t.band
        slack = RUN_TOLERANCE * (hi - lo)
        m = mean(vs)
        ok = lo <= m <= hi and min(vs) >= lo - slack and max(vs) <= hi + slack
        rows.append(Row(t, m, min(vs), max(vs), ok))
    return rows


def format_table(rows: list[Row]) -> str:
    lines = [f"{'metric':24}{'band':>16}{'mean':>9}{'min':>9}{'max':>9}  result"]
    for r in rows:
        band = f"{r.target.band[0]:g} to {r.target.band[1]:g}"
        lines.append(
            f"{r.target.id:24}{band:>16}{r.mean:>9.3f}{r.low:>9.3f}{r.high:>9.3f}  {'pass' if r.ok else 'fail'}"
        )
    return "\n".join(lines)


def report_json(rows: list[Row], seeds: list[int], git_sha: str) -> str:
    return json.dumps(
        {
            "seeds": seeds,
            "storylines": sorted(STORYLINES),
            "git_sha": git_sha,
            "metrics": [
                {
                    "id": r.target.id,
                    "per": r.target.per,
                    "unit": r.target.unit,
                    "band": list(r.target.band),
                    "source": r.target.source,
                    "status": r.target.status,
                    "mean": round(r.mean, 4),
                    "min": round(r.low, 4),
                    "max": round(r.high, 4),
                    "pass": r.ok,
                }
                for r in rows
            ],
        },
        indent=2,
    )
