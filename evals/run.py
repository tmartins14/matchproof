"""Run the adversarial claims through the Checker with a judge, or compare every candidate.

    uv run python -m evals.run --judge judge-mai      # make evals JUDGE=judge-mai
    uv run python -m evals.run --bakeoff              # make bakeoff

Calls real models. A bad claim is caught when its first check does not pass it, whether the
reconciler, the voice lint or the judge stopped it. Judge latency is the wall time of the judge
step (every attempt) for each claim that reached the judge, including calls that timed out.
"""

import argparse
import json
import math
import statistics
import time
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from agents.checker import Checker, ClaimCheck
from agents.llm_client import MODELS_PATH, client_for, load_models
from agents.narrator import DraftClaim
from contracts.models import Fact
from mcp_match import InMemoryMatchStore

from .golden import build_store
from .pick import RULE_TEXT, Score, pick_judge, set_active_judge

ROOT = Path(__file__).resolve().parents[1]
CLAIMS_PATH = ROOT / "evals" / "adversarial" / "claims.yaml"
REPORTS_DIR = ROOT / "evals" / "reports"


@dataclass
class ClaimResult:
    id: str
    kind: str
    expected: str
    text: str
    passed_first_check: bool
    stopped_by: str  # code | judge | judge_unavailable | none
    reasons: list[str]
    judge_problem: str | None = None
    judge_ms: int | None = None
    tokens: int = 0


@dataclass
class Report:
    deployment: str
    date: str
    bad_total: int = 0
    caught: int = 0
    caught_by_code: int = 0
    caught_by_judge: int = 0
    judge_unavailable: int = 0
    good_total: int = 0
    good_blocked: int = 0
    judge_calls: int = 0
    p50_ms: int = 0
    p90_ms: int = 0
    tokens_per_claim: float = 0.0
    results: list[ClaimResult] = field(default_factory=list)


def percentile(values: list[int], q: float) -> int:
    """Nearest-rank percentile."""
    if not values:
        return 0
    ordered = sorted(values)
    rank = max(1, math.ceil(q * len(ordered)))
    return ordered[rank - 1]


def load_claims() -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = yaml.safe_load(CLAIMS_PATH.read_text("utf-8"))
    return claims


def stores_for(
    claims: list[dict[str, Any]],
) -> dict[tuple[str, int], tuple[InMemoryMatchStore, str]]:
    out: dict[tuple[str, int], tuple[InMemoryMatchStore, str]] = {}
    for c in claims:
        key = (c["match"]["story"], c["match"]["seed"])
        if key not in out:
            out[key] = build_store(*key)
    return out


def bundle_for(
    store: InMemoryMatchStore, match_id: str, beat_id: str
) -> tuple[dict[str, Fact], str, str, dict[str, str]]:
    beat = next(b for b in store.beats(match_id) if b.id.root == beat_id)
    registry = store.registry(match_id)
    facts = {f.root: registry.get(f.root) for f in beat.fact_ids}
    brief = store.brief(match_id)
    teams = {"home": brief.home.name, "away": brief.away.name}
    return facts, beat.kind.value, beat.label, teams


def run_judge(
    deployment: str,
    claims: list[dict[str, Any]],
    stores: dict[tuple[str, int], tuple[InMemoryMatchStore, str]],
) -> Report:
    client = client_for("judge", deployment=deployment)
    checker = Checker(client, timeout_s=client.settings.timeout_s)
    report = Report(deployment=deployment, date=date.today().isoformat())
    latencies: list[int] = []
    tokens: list[int] = []
    for c in claims:
        store, match_id = stores[(c["match"]["story"], c["match"]["seed"])]
        facts, kind, label, teams = bundle_for(store, match_id, c["beat_id"])
        draft = DraftClaim.model_construct(text=c["text"], fact_ids=list(c["fact_ids"]))
        started = time.perf_counter()
        check: ClaimCheck = checker.check_one(
            draft, facts, teams=teams, beat_kind=kind, beat_label=label
        )
        wall_ms = round((time.perf_counter() - started) * 1000)
        bad = c["expected"] != "verified"
        if check.passed:
            stopped = "none"
        elif check.caught_by_code:
            stopped = "code"
        elif check.delayed:
            stopped = "judge_unavailable"
        else:
            stopped = "judge"
        if check.judged:
            latencies.append(wall_ms)
            tokens.append(check.input_tokens + check.output_tokens)
        result = ClaimResult(
            c["id"],
            c["kind"],
            c["expected"],
            c["text"],
            check.passed,
            stopped,
            check.reasons,
            check.judge_problem,
            wall_ms if check.judged else None,
            check.input_tokens + check.output_tokens,
        )
        report.results.append(result)
        if bad:
            report.bad_total += 1
            report.caught += stopped in ("code", "judge")
            report.caught_by_code += stopped == "code"
            report.caught_by_judge += stopped == "judge"
        else:
            report.good_total += 1
            report.good_blocked += stopped in ("code", "judge")
        report.judge_unavailable += stopped == "judge_unavailable"
        print(
            f"  {c['id']:8} {c['kind']:17} -> {stopped:17} {wall_ms:6} ms", flush=True
        )
    report.judge_calls = len(latencies)
    report.p50_ms = round(statistics.median(latencies)) if latencies else 0
    report.p90_ms = percentile(latencies, 0.9)
    report.tokens_per_claim = round(sum(tokens) / len(tokens), 1) if tokens else 0.0
    return report


def write_report(report: Report) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"{report.date}-{report.deployment}.json"
    path.write_text(json.dumps(asdict(report), indent=2) + "\n", "utf-8")
    return path


def bakeoff_table(reports: list[Report]) -> str:
    head = (
        "| Judge | Bad caught (of 30) | by code | by judge | Good wrongly blocked (of 10) | "
        "Judge unavailable | p50 | p90 | Tokens per claim |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
    )
    rows = "".join(
        f"| {r.deployment} | {r.caught} | {r.caught_by_code} | {r.caught_by_judge} | {r.good_blocked} | "
        f"{r.judge_unavailable} | {r.p50_ms / 1000:.1f} s | {r.p90_ms / 1000:.1f} s | {r.tokens_per_claim} |\n"
        for r in reports
    )
    return head + rows


def write_bakeoff(
    reports: list[Report], winner: str, reason: str, fallback: bool
) -> Path:
    path = REPORTS_DIR / "bakeoff.md"
    note = (
        "\nNo candidate qualified, so the fallback judge is active.\n"
        if fallback
        else ""
    )
    path.write_text(
        f"# Judge bake-off, {reports[0].date}\n\n"
        f"Rule: {RULE_TEXT}. Pick made by `evals/pick.py`.\n\n"
        f"{bakeoff_table(reports)}\n"
        f"Winner: **{winner}**. {reason}.{note}\n"
        "Bad claims are caught by code (reconciler or voice lint, no model call) or by the judge. "
        "Latency is the judge step's wall time per claim that reached the judge.\n",
        "utf-8",
    )
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--judge", help="one judge deployment")
    group.add_argument(
        "--bakeoff", action="store_true", help="every candidate, then pick"
    )
    args = parser.parse_args()
    claims = load_claims()
    stores = stores_for(claims)
    models = load_models()
    if args.judge:
        report = run_judge(args.judge, claims, stores)
        print(write_report(report))
        print(bakeoff_table([report]))
        return
    reports: list[Report] = []
    for entry in models["judge_candidates"]:
        print(entry["deployment"], flush=True)
        reports.append(run_judge(entry["deployment"], claims, stores))
        write_report(reports[-1])
    scores = [Score(r.deployment, r.caught, r.good_blocked, r.p90_ms) for r in reports]
    pick = pick_judge(scores)
    if pick.fallback:
        print(pick.deployment, flush=True)
        reports.append(run_judge(pick.deployment, claims, stores))
        write_report(reports[-1])
    set_active_judge(MODELS_PATH, pick.deployment)
    print(write_bakeoff(reports, pick.deployment, pick.reason, pick.fallback))
    print(bakeoff_table(reports))


if __name__ == "__main__":
    main()
