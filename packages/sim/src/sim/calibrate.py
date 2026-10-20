"""Calibration report: run every storyline on each seed with default tactics and compare to bands."""

import json
import math
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, median

import yaml
from contracts.models import Event, MatchBrief, PositionFrame

from . import generate, geometry
from .brief import STORYLINES, make_brief
from .positions import iter_frames

TARGETS_PATH = Path(__file__).resolve().parents[2] / "calibration" / "targets.yaml"
# Without a match band, a single run may sit outside the band by at most this share of the band width.
RUN_TOLERANCE = 0.15
# Where a reference mean is set, the mean across runs must be within this share of it.
MEAN_TOLERANCE = 0.12
SAMPLE_EVERY = 5  # 5 Hz frames sampled at 1 Hz
MID_BLOCK_BALL_M = (
    35.0,
    85.0,
)  # ball distance from the defending goal that counts as a mid-block
# Not targets: per team and match, in-possession shape minus out-of-possession shape, for the shape rules.
SHAPE_GAIN_KEYS = ("back_line_gain", "length_gain")


@dataclass(frozen=True)
class Target:
    id: str
    per: str
    band: tuple[float, float]
    unit: str
    source: str
    status: str
    reference_mean: float | None = None
    note: str = ""
    match_band: tuple[float, float] | None = None


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
            None if r.get("reference_mean") is None else float(r["reference_mean"]),
            r.get("note", ""),
            None
            if r.get("match_band") is None
            else (float(r["match_band"][0]), float(r["match_band"][1])),
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


def _median(xs: list[float]) -> float:
    return median(xs) if xs else float("nan")


def shape_metrics(frames: Iterable[PositionFrame]) -> dict[str, list[float]]:
    """Positional metrics for one match, two values per metric (home, then away), from frames sampled at 1 Hz."""
    series: dict[str, dict[str, list[float]]] = {}

    def add(side: str, key: str, value: float) -> None:
        series.setdefault(key, {}).setdefault(side, []).append(value)

    for i, frame in enumerate(frames):
        if i % SAMPLE_EVERY or frame.possession is None:
            continue
        poss = frame.possession.value
        bx, by = frame.ball.root[0].root, frame.ball.root[1].root
        for side in ("home", "away"):
            pts = geometry.outfield_points(frame, side)
            if len(pts) < 3:
                continue
            if side == poss:
                add(side, "back_line_height_in", geometry.back_line_height(pts, side))
                add(side, "team_length_in", geometry.team_length(pts))
                continue
            add(side, "back_line_height_out", geometry.back_line_height(pts, side))
            add(side, "compactness_out", geometry.hull_area(pts))
            goal_x = 0.0 if side == "home" else geometry.PITCH_LENGTH
            if (
                MID_BLOCK_BALL_M[0]
                <= math.hypot(bx - goal_x, by - 40.0)
                <= MID_BLOCK_BALL_M[1]
            ):
                add(side, "team_length_out", geometry.team_length(pts))
                add(side, "team_width_out", geometry.team_width(pts))
            add(side, "team_length_out_all", geometry.team_length(pts))
    out: dict[str, list[float]] = {}
    for key in (
        "back_line_height_out",
        "back_line_height_in",
        "team_length_out",
        "team_width_out",
        "compactness_out",
    ):
        for side in ("home", "away"):
            out.setdefault(key, []).append(_median(series.get(key, {}).get(side, [])))
    for side in ("home", "away"):
        med = {k: _median(series.get(k, {}).get(side, [])) for k in series}
        out.setdefault("back_line_gain", []).append(
            med["back_line_height_in"] - med["back_line_height_out"]
        )
        out.setdefault("length_gain", []).append(
            med["team_length_in"] - med["team_length_out_all"]
        )
    return out


def match_values(brief: MatchBrief) -> dict[str, list[float]]:
    events = generate(brief)
    return match_metrics(events) | shape_metrics(iter_frames(brief, events))


def collect(seeds: list[int]) -> dict[str, list[float]]:
    values: dict[str, list[float]] = {}
    for story in sorted(STORYLINES):
        for seed in seeds:
            for key, vs in match_values(
                make_brief(storyline_id=story, seed=seed)
            ).items():
                values.setdefault(key, []).extend(vs)
    return values


def run_limits(t: Target) -> tuple[float, float]:
    """Where a single run may sit: the match band if there is one, else the band plus 15% of its width."""
    if t.match_band is not None:
        return t.match_band
    slack = RUN_TOLERANCE * (t.band[1] - t.band[0])
    return (t.band[0] - slack, t.band[1] + slack)


def evaluate(values: dict[str, list[float]], targets: list[Target]) -> list[Row]:
    rows: list[Row] = []
    for t in targets:
        vs = values[t.id]
        lo, hi = t.band
        run_lo, run_hi = run_limits(t)
        m = mean(vs)
        ok = lo <= m <= hi and min(vs) >= run_lo and max(vs) <= run_hi
        if t.reference_mean is not None:
            ok = ok and abs(m - t.reference_mean) <= MEAN_TOLERANCE * abs(
                t.reference_mean
            )
        rows.append(Row(t, m, min(vs), max(vs), ok))
    return rows


def format_table(rows: list[Row]) -> str:
    lines = [
        f"{'metric':24}{'band':>16}{'ref':>9}{'mean':>9}{'min':>9}{'max':>9}  result"
    ]
    for r in rows:
        band = f"{r.target.band[0]:g} to {r.target.band[1]:g}"
        ref = "-" if r.target.reference_mean is None else f"{r.target.reference_mean:g}"
        lines.append(
            f"{r.target.id:24}{band:>16}{ref:>9}{r.mean:>9.3f}{r.low:>9.3f}{r.high:>9.3f}  {'pass' if r.ok else 'fail'}"
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
                    "match_band": None
                    if r.target.match_band is None
                    else list(r.target.match_band),
                    "source": r.target.source,
                    "status": r.target.status,
                    "reference_mean": r.target.reference_mean,
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
