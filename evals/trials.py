"""Narrator Trials: a fixed pack of seeded matches, a field of candidate narrators, one referee.

Every candidate narrates every beat of every fixture with the same prompt. The Checker, the inline
judge, the auditor and consensus are the referee; the verdict that counts is the one on air after
consensus. Everything here is computed in Python (seam rule 1); the browser only draws the JSON.

uv run python -m evals.trials                                            # pack-v1, every candidate
uv run python -m evals.trials --candidates gpt-5-mini --fixtures fx-01   # the smoke
uv run python -m evals.trials --no-audit                                 # skip the auditor, a dry run
"""

import argparse
import asyncio
import difflib
import hashlib
import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from agents.auditor import MAX_CONCURRENT_AUDITS, Auditor
from agents.budget import MeteredClient, TokenBudget
from agents.checker import VOICE_REASON_PREFIX, CheckedClaim
from agents.consensus import Consensus
from agents.llm_client import LlmError, client_for, load_models
from agents.narrator import PROMPT_PATH
from agents.pipeline import BeatRun, Deps, run_beat
from agents.prices import NOT_SET, cost_of, load_prices
from agents.reconcile import (
    COMPARES_REASON,
    NO_FACTS_REASON,
    NOT_IN_BUNDLE_REASON,
    NUMBER_REASON_PREFIX,
    PLAYER_REASON_PREFIX,
)
from agents.structured import StructuredOutputError
from contracts.models import Audit, Claim, MatchBrief, TrialsResults
from intel.display import minute_of
from intel.voice_lint import numbers_in
from mcp_match import InMemoryMatchStore, build_server
from sim.brief import (
    DEFAULT_AWAY,
    DEFAULT_HOME,
    STORYLINES,
    PlantedSpec,
    final_score,
    make_brief,
    validate_planted,
)

from .golden import build_store_from_brief
from .run import REPORTS_DIR, ROOT, percentile

PACK_PATH = Path(__file__).parent / "trials" / "pack_v1.yaml"
TRIALS_DIR = REPORTS_DIR / "trials"
WEB_FIXTURES_DIR = ROOT / "apps" / "web" / "fixtures" / "trials"
BLOB_CONTAINER = "trials"
DEFAULT_PARALLEL = 3
# The workflow keeps one entry per match and beat while it runs, so two candidates on the same beat of
# the same fixture at the same moment would collide. Same-beat runs take turns; the candidates then
# fall a beat apart and run side by side.
_BEAT_LOCKS: dict[str, asyncio.Lock] = {}
NO_CAP = 10**12  # the daily token cap is for the live desk, not for a trial run

# Checker verdict (after consensus) to Trials verdict, and the points each is worth.
TRIAL_VERDICT = {
    "verified": "STANDS",
    "rephrased": "AMENDED",
    "blocked": "OVERTURNED",
    "delayed": "HELD",
}
POINTS = {"STANDS": 3, "AMENDED": 1, "OVERTURNED": -3, "HELD": 0}
FORM_LETTER = {"STANDS": "S", "AMENDED": "A", "OVERTURNED": "O", "HELD": "H"}
FORM_LENGTH = 5
OVERCLAIM_PROBLEMS = ("overclaim", "motive", "unsupported_cause", "outside_knowledge")
SETTLED = ("verified", "rephrased")  # the claims the auditor looks at


def trial_verdict(checker_verdict: str) -> str:
    return TRIAL_VERDICT[checker_verdict]


def reason_bucket(reasons: list[str], judge_problem: str | None) -> str:
    """Why a claim did not stand, from the first check's reasons and the judge's `problem` field.
    First match wins; no model classifies anything."""
    if any(r.startswith(NUMBER_REASON_PREFIX) for r in reasons):
        return "numbers"
    if any(r.startswith(PLAYER_REASON_PREFIX) for r in reasons):
        return "names"
    if any(r == NO_FACTS_REASON or r.endswith(NOT_IN_BUNDLE_REASON) for r in reasons):
        return "citation"
    if judge_problem == "wrong_entity":
        return "attribution"
    if judge_problem == "wrong_time":
        return "timing"
    if judge_problem in OVERCLAIM_PROBLEMS or any(
        COMPARES_REASON in r for r in reasons
    ):
        return "overclaim"
    if any(r.startswith(VOICE_REASON_PREFIX) for r in reasons):
        return "wording"
    return "other"


def differing_span(draft: str, text: str) -> tuple[str | None, str | None]:
    """The shortest run of words that covers every difference between the two wordings."""
    a, b = draft.split(), text.split()
    changes = [
        op
        for op in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes()
        if op[0] != "equal"
    ]
    if not changes:
        return None, None
    i1, i2 = changes[0][1], changes[-1][2]
    j1, j2 = changes[0][3], changes[-1][4]
    return " ".join(a[i1:i2]), " ".join(b[j1:j2])


def prompt_hash() -> str:
    """First 8 hex of the SHA-256 of the narrator prompt as loaded."""
    return hashlib.sha256(PROMPT_PATH.read_text("utf-8").encode()).hexdigest()[:8]


def git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


# ---- the pack ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Fixture:
    id: str
    seed: int
    storyline: str
    planted: tuple[PlantedSpec, ...]  # the moments the match plants, preset or custom
    brief_line: str
    traps: tuple[dict[str, Any], ...]

    def make_brief(self) -> MatchBrief:
        custom = self.storyline == "custom"
        return make_brief(
            DEFAULT_HOME,
            DEFAULT_AWAY,
            self.storyline,
            self.seed,
            list(self.planted) if custom else None,
        )


def load_pack(path: Path = PACK_PATH) -> tuple[str, list[Fixture]]:
    raw: dict[str, Any] = yaml.safe_load(path.read_text("utf-8"))
    fixtures = []
    for f in raw["fixtures"]:
        planted = tuple(
            (str(k), str(s), int(a), int(b))
            for k, s, a, b in f.get("planted") or STORYLINES[f["storyline"]].beats
        )
        fixtures.append(
            Fixture(
                f["id"],
                int(f["seed"]),
                f["storyline"],
                planted,
                f["brief"],
                tuple(f["traps"]),
            )
        )
    return str(raw["pack"]), fixtures


def check_pack(fixtures: list[Fixture]) -> list[str]:
    """Why a fixture cannot be played, in plain English; empty when the pack is sound."""
    errors: list[str] = []
    for f in fixtures:
        errors += [f"{f.id}: {e}" for e in validate_planted(f.planted)]
        for trap in f.traps:
            n = int(trap["planted"])
            if not 1 <= n <= len(f.planted) or f.planted[n - 1][0] != trap["kind"]:
                errors.append(f"{f.id}: trap {trap['kind']} is not moment {n}.")
    return errors


def describe_fixture(
    f: Fixture, store: InMemoryMatchStore, match_id: str
) -> dict[str, Any]:
    """The fixture as the results file shows it. A trap's minute and event come from the planted
    beat in the generated match, never from the pack file."""
    brief = store.brief(match_id)
    beats = {b.planted_beat_id: b for b in store.beats(match_id) if b.planted_beat_id}
    events = {e.id.root: e for e in store.events(match_id)}
    traps = []
    for trap in f.traps:
        beat = beats[f"pb-{int(trap['planted']):02d}"]
        anchor = events[beat.anchor_event_id.root]
        traps.append(
            {
                "minute": minute_of(anchor.t.root),
                "kind": trap["kind"],
                "note": trap["note"],
                "event_id": anchor.id.root,
            }
        )
    home, away = final_score(f.planted)
    return {
        "id": f.id,
        "seed": f.seed,
        "match_id": match_id,
        "home": brief.home.short,
        "away": brief.away.short,
        "brief": f.brief_line,
        "final_score": [home, away],
        "traps": traps,
    }


# ---- one candidate on one fixture ----------------------------------------------------------------


@dataclass
class FixtureRun:
    claims: list[dict[str, Any]] = field(default_factory=list)
    latencies: list[int] = field(default_factory=list)
    usage: dict[str, Any] = field(
        default_factory=dict
    )  # the candidate's Narrator usage
    errors: list[str] = field(default_factory=list)


def audit_label(audit: Audit | None) -> str:
    if audit is None:
        return "not audited"
    if audit.outcome.value == "disagree":
        return f"disagree ({audit.problem})"
    return audit.outcome.value


def numbers_note(claim: Claim) -> str:
    total = len(numbers_in(claim.text))
    return f"{len(claim.numbers)}/{total} numbers matched" if total else "no numbers"


def claim_row(
    fixture: str,
    candidate: str,
    minute: int,
    run: BeatRun,
    checked: CheckedClaim,
    index: int,
    *,
    audit: Audit | None = None,
    corrected: Claim | None = None,
) -> dict[str, Any]:
    """One claim as the results file records it. `corrected` is the replacement consensus made."""
    claim = corrected or checked.claim
    verdict = trial_verdict(claim.verdict.value)
    draft = checked.claim.draft_text or checked.claim.text
    reasons: list[str] = []
    bucket: str | None = None
    if verdict in ("AMENDED", "OVERTURNED"):
        if corrected is not None:
            reasons = [corrected.reason] if corrected.reason else []
            bucket = reason_bucket(reasons, audit.problem if audit else None)
        else:
            reasons = list(checked.first.reasons)
            bucket = reason_bucket(reasons, checked.first.judge_problem)
    failed = repaired = None
    if verdict == "AMENDED":
        failed, repaired = differing_span(draft, claim.text)
    return {
        "id": claim.id.root,
        "fixture": fixture,
        "beat": claim.beat_id.root,
        "minute": minute,
        "candidate": candidate,
        "scored": index == 0,
        "text": claim.text,
        "draft_text": draft,
        "verdict": verdict,
        "reason_bucket": bucket,
        "reasons": reasons,
        "failed_span": failed,
        "corrected_span": repaired,
        "fact_ids": [f.root for f in claim.fact_ids],
        "checker": numbers_note(claim),
        "auditor": audit_label(audit),
        "corrected_by_consensus": corrected is not None,
        "latency_ms": run.latency_ms,
        "tokens_in": sum(c.input_tokens for c in run.narrator_calls),
        "tokens_out": sum(c.output_tokens for c in run.narrator_calls),
    }


async def play_fixture(
    candidate: str,
    fixture: Fixture,
    *,
    judge_client: Any,
    auditor_client: Any,
    gate: asyncio.Semaphore,
    audit: bool,
) -> FixtureRun:
    """Every beat of one fixture through the workflow with `candidate` as the Narrator, then the
    auditor and consensus on what the Checker settled."""
    out = FixtureRun()
    store, match_id = build_store_from_brief(fixture.make_brief())
    server = build_server(store, writable=True)
    counter = TokenBudget(NO_CAP)  # the candidate's own usage, for its cost
    narrator = MeteredClient(
        client_for("narrator", deployment=candidate), "narrator", counter=counter
    )
    deps = Deps(server, narrator, judge_client)
    beats = {b.id.root: b for b in store.beats(match_id)}
    runs: list[tuple[str, BeatRun]] = []
    for beat in beats.values():
        try:
            async with _BEAT_LOCKS.setdefault(
                f"{match_id}/{beat.id.root}", asyncio.Lock()
            ):
                run = await run_beat(match_id, beat.id.root, "fan", deps=deps)
        except (LlmError, StructuredOutputError, OSError, ValueError) as exc:
            out.errors.append(f"{beat.id.root}: {type(exc).__name__}({exc})")
            continue
        out.latencies.append(run.latency_ms)
        if run.error or not run.checked:
            out.errors.append(f"{beat.id.root}: {run.error or 'no claims'}")
        runs.append((beat.id.root, run))

    auditor = Auditor(auditor_client, server)
    consensus = Consensus(judge_client, narrator, server)

    async def settle(
        beat_id: str, checked: CheckedClaim
    ) -> tuple[Audit | None, Claim | None]:
        if not audit or checked.claim.verdict.value not in SETTLED:
            return None, None
        async with gate:
            result = await auditor.audit(match_id, checked.claim)
            if result.outcome.value != "disagree":
                return result, None
            outcome = await consensus.review(
                match_id, checked.claim, result, beats[beat_id].t_detect.root
            )
        return result, outcome.claim

    settled = await asyncio.gather(
        *(settle(bid, c) for bid, r in runs for c in r.checked)
    )
    results = iter(settled)
    for beat_id, run in runs:
        minute = minute_of(beats[beat_id].t_detect.root)
        for i, checked in enumerate(run.checked):
            result, corrected = next(results)
            out.claims.append(
                claim_row(
                    fixture.id,
                    candidate,
                    minute,
                    run,
                    checked,
                    i,
                    audit=result,
                    corrected=corrected,
                )
            )
    out.usage = counter.snapshot()["usage"]
    return out


async def play_candidate(
    candidate: str,
    fixtures: list[Fixture],
    *,
    judge_client: Any,
    auditor_client: Any,
    gate: asyncio.Semaphore,
    audit: bool,
    pace: asyncio.Semaphore,
) -> dict[str, FixtureRun | str]:
    """One candidate through the fixtures in order. A fixture that errors is recorded as such."""
    async with pace:
        runs: dict[str, FixtureRun | str] = {}
        for fixture in fixtures:
            started = time.perf_counter()
            try:
                runs[fixture.id] = await play_fixture(
                    candidate,
                    fixture,
                    judge_client=judge_client,
                    auditor_client=auditor_client,
                    gate=gate,
                    audit=audit,
                )
            except (LlmError, StructuredOutputError, OSError, ValueError) as exc:
                runs[fixture.id] = f"{type(exc).__name__}({exc})"
            print(
                f"{candidate} {fixture.id} done in {time.perf_counter() - started:.0f}s",
                flush=True,
            )
        return runs


# ---- the table ---------------------------------------------------------------------------------


def fail_profile(scored: list[dict[str, Any]]) -> dict[str, float]:
    """Share of the scored claims that failed (not STANDS, not HELD) in each bucket; sums to 1."""
    buckets = [
        c["reason_bucket"] for c in scored if c["verdict"] in ("AMENDED", "OVERTURNED")
    ]
    if not buckets:
        return {}
    shares = {
        b: round(buckets.count(b) / len(buckets), 3) for b in dict.fromkeys(buckets)
    }
    biggest = max(shares, key=lambda b: shares[b])
    shares[biggest] = round(shares[biggest] + 1 - sum(shares.values()), 3)
    return shares


def clean_pct(rows: list[dict[str, Any]]) -> float | None:
    counted = [c for c in rows if c["verdict"] != "HELD"]
    if not counted:
        return None
    stands = sum(c["verdict"] == "STANDS" for c in counted)
    return float(round(100 * stands / len(counted), 1))


def summarize_candidate(
    candidate: str,
    claims: list[dict[str, Any]],
    fixture_ids: list[str],
    latencies: list[int],
    usages: list[dict[str, Any]],
) -> dict[str, Any]:
    """The candidate's row of the league table. `usages` is its Narrator usage per fixture played."""
    scored = [c for c in claims if c["candidate"] == candidate and c["scored"]]
    count = {v: sum(c["verdict"] == v for c in scored) for v in POINTS}
    costs = [cost_of(u) for u in usages]
    usd: float | str = NOT_SET
    if costs and all(isinstance(c, dict) for c in costs):
        usd = round(
            sum(c["total"] for c in costs if isinstance(c, dict)) / len(costs), 4
        )
    tokens = [sum(r["input"] + r["output"] for r in u.values()) for u in usages]
    verdicts = [c["auditor"] for c in claims if c["candidate"] == candidate]
    audited = [a for a in verdicts if a == "agree" or a.startswith("disagree")]
    by_fixture = {}
    form = []
    for fid in fixture_ids:
        rows = [c for c in scored if c["fixture"] == fid]
        if rows:
            by_fixture[fid] = {
                "pts": sum(POINTS[c["verdict"]] for c in rows),
                "clean_pct": clean_pct(rows),
            }
    for fid in fixture_ids[-FORM_LENGTH:]:
        rows = [c for c in scored if c["fixture"] == fid]
        if rows:
            form.append(FORM_LETTER[rows[-1]["verdict"]])
    return {
        "candidate": candidate,
        "claims": len(scored),
        "stands": count["STANDS"],
        "amended": count["AMENDED"],
        "overturned": count["OVERTURNED"],
        "held": count["HELD"],
        "pts": sum(POINTS[c["verdict"]] for c in scored),
        "clean_pct": clean_pct(scored),
        "p90_ms": percentile(latencies, 0.9),
        "usd_per_match": usd,
        "tokens_per_match": round(sum(tokens) / len(tokens)) if tokens else 0,
        "cleared": count["OVERTURNED"] <= count["AMENDED"],
        "fail_profile": fail_profile(scored),
        "form": form,
        "by_fixture": by_fixture,
        "audit_agreement": (
            round(audited.count("agree") / len(audited), 3) if audited else None
        ),
    }


def rank(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """By pts, then clean_pct, then p90_ms."""
    return sorted(
        rows,
        key=lambda r: (
            -r["pts"],
            -(r["clean_pct"] if r["clean_pct"] is not None else -1),
            r["p90_ms"],
        ),
    )


def markdown(results: dict[str, Any]) -> str:
    """The table, and every OVERTURNED claim with its reason."""
    lines = [
        f"# Narrator Trials, {results['pack']}",
        "",
        (
            f"Run {results['run_at']} at {results['git_sha']}. Judge {results['referee']['judge']},"
            f" auditor {results['referee']['auditor']}. Referee cost: {_money(results['referee']['cost'])}."
        ),
        "",
        "| # | Candidate | Pts | Clean | Stands | Amended | Overturned | Held | p90 | USD/match | Auditor agrees | |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    own = {c["id"]: c["self_audited"] for c in results["candidates"]}
    for i, r in enumerate(results["summary"], 1):
        agree = (
            "n/a"
            if r["audit_agreement"] is None
            else f"{100 * r['audit_agreement']:.0f}%"
        )
        clean = "n/a" if r["clean_pct"] is None else f"{r['clean_pct']}%"
        usd = (
            r["usd_per_match"]
            if isinstance(r["usd_per_match"], str)
            else f"{r['usd_per_match']:.4f}"
        )
        note = ("Cleared for air" if r["cleared"] else "Not cleared for air") + (
            "; audited by its own model" if own[r["candidate"]] else ""
        )
        lines.append(
            f"| {i} | {r['candidate']} | {r['pts']} | {clean} | {r['stands']} | {r['amended']} |"
            f" {r['overturned']} | {r['held']} | {r['p90_ms']} ms | {usd} | {agree} | {note} |"
        )
    if results["errors"]:
        lines += ["", "## Errors", ""]
        lines += [
            f"- {e['candidate']} {e['fixture']}: {e['error']}"
            for e in results["errors"]
        ]
    lines += ["", "## Overturned", ""]
    overturned = [c for c in results["claims"] if c["verdict"] == "OVERTURNED"]
    for c in overturned:
        stamp = "" if c["scored"] else " (not scored)"
        lines.append(
            f"- **{c['candidate']}** {c['fixture']} {c['minute']}′{stamp}: {c['text']}"
            f" [{c['reason_bucket']}] {'; '.join(c['reasons'])}"
        )
    if not overturned:
        lines.append("None.")
    return "\n".join(lines) + "\n"


def _money(cost: Any) -> str:
    if isinstance(cost, str):
        return cost
    return f"{cost['total']:.4f} {cost['currency']}"


# ---- the run -----------------------------------------------------------------------------------


def candidate_entry(entry: dict[str, Any], auditor_deployment: str) -> dict[str, Any]:
    price = load_prices().get(entry["deployment"])
    return {
        "id": entry["id"],
        "deployment": entry["deployment"],
        "model": entry["model"],
        "prompt_hash": prompt_hash(),
        "price_in": price.input_per_million if price else None,
        "price_out": price.output_per_million if price else None,
        "currency": price.currency if price else None,
        "self_audited": entry["deployment"] == auditor_deployment,
    }


async def run_trials(
    candidates: list[str],
    fixtures: list[Fixture],
    pack: str,
    *,
    parallel: int,
    audit: bool,
) -> dict[str, Any]:
    models = load_models()
    auditor_deployment = str(models["auditor"]["deployment"])
    entries = {e["id"]: e for e in models["trial_candidates"]}
    unknown = [c for c in candidates if c not in entries]
    if unknown:
        raise LlmError("UnknownCandidate")
    # One referee for everyone; its cost is reported once.
    referee = TokenBudget(NO_CAP)
    judge_client = MeteredClient(client_for("judge"), "judge", counter=referee)
    auditor_client = MeteredClient(client_for("auditor"), "auditor", counter=referee)
    gate = asyncio.Semaphore(MAX_CONCURRENT_AUDITS)
    pace = asyncio.Semaphore(parallel)

    meta = []
    for f in fixtures:
        store, match_id = build_store_from_brief(f.make_brief())
        meta.append(describe_fixture(f, store, match_id))
        print(f"{f.id} built: {match_id}", flush=True)

    played = await asyncio.gather(
        *(
            play_candidate(
                c,
                fixtures,
                judge_client=judge_client,
                auditor_client=auditor_client,
                gate=gate,
                audit=audit,
                pace=pace,
            )
            for c in candidates
        )
    )
    claims: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    summary: list[dict[str, Any]] = []
    fixture_ids = [f.id for f in fixtures]
    for candidate, runs in zip(candidates, played, strict=True):
        latencies: list[int] = []
        usages: list[dict[str, Any]] = []
        for fid in fixture_ids:
            run = runs[fid]
            if isinstance(run, str):
                errors.append({"candidate": candidate, "fixture": fid, "error": run})
                continue
            claims += run.claims
            latencies += run.latencies
            usages.append(run.usage)
            errors += [
                {"candidate": candidate, "fixture": fid, "error": e} for e in run.errors
            ]
        summary.append(
            summarize_candidate(candidate, claims, fixture_ids, latencies, usages)
        )
    snapshot = referee.snapshot()
    judge_name = judge_client.deployment
    auditor_label = next(
        (
            f"{auditor_deployment} ({e['id']})"
            for e in entries.values()
            if e["deployment"] == auditor_deployment
        ),
        auditor_deployment,
    )
    return {
        "pack": pack,
        "run_at": datetime.now(UTC)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "git_sha": git_sha(),
        "referee": {
            "checker": "code",
            "judge": judge_name,
            "auditor": auditor_label,
            "judge_prompt": str(models["judge_prompt"]),
            "audited": audit,
            "cost": snapshot["cost"],
        },
        "fixtures": meta,
        "candidates": [
            candidate_entry(entries[c], auditor_deployment) for c in candidates
        ],
        "claims": claims,
        "errors": errors,
        "summary": rank(summary),
    }


def upload(paths: list[Path]) -> None:
    """Put the files in the `trials` container of the storage account, with managed identity."""
    from azure.core.exceptions import ResourceExistsError
    from azure.identity import DefaultAzureCredential
    from azure.storage.blob import BlobServiceClient

    account = os.environ.get("AZURE_STORAGE_ACCOUNT")
    if not account:
        raise LlmError("MissingStorageConfig")
    service = BlobServiceClient(
        f"https://{account}.blob.core.windows.net", credential=DefaultAzureCredential()
    )
    container = service.get_container_client(BLOB_CONTAINER)
    try:
        container.create_container()
    except ResourceExistsError:
        pass
    for path in paths:
        container.upload_blob(path.name, path.read_bytes(), overwrite=True)
        print(f"uploaded {BLOB_CONTAINER}/{path.name}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--candidates", help="comma-separated candidate ids; default every one"
    )
    parser.add_argument(
        "--fixtures", help="comma-separated fixture ids; default the whole pack"
    )
    parser.add_argument("--parallel", type=int, default=DEFAULT_PARALLEL)
    parser.add_argument("--no-audit", action="store_true")
    parser.add_argument(
        "--upload", action="store_true", help="copy the results to Blob trials/"
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="copy the JSON to apps/web/fixtures/trials/",
    )
    args = parser.parse_args()

    pack, fixtures = load_pack()
    problems = check_pack(fixtures)
    if problems:
        raise SystemExit("\n".join(problems))
    models = load_models()
    candidates = (
        args.candidates.split(",")
        if args.candidates
        else [e["id"] for e in models["trial_candidates"]]
    )
    if args.fixtures:
        wanted = args.fixtures.split(",")
        fixtures = [f for f in fixtures if f.id in wanted]
    full = not args.candidates and not args.fixtures and not args.no_audit
    if (args.upload or args.publish) and not full:
        raise SystemExit(
            "--upload and --publish need the full pack, every candidate, with the audit."
        )

    started = time.perf_counter()
    results = asyncio.run(
        run_trials(
            candidates, fixtures, pack, parallel=args.parallel, audit=not args.no_audit
        )
    )
    TrialsResults.model_validate(results)  # the contract, before anything is written
    TRIALS_DIR.mkdir(parents=True, exist_ok=True)
    stem = pack if full else f"{pack}-{'dry' if args.no_audit else 'smoke'}"
    json_path, md_path = TRIALS_DIR / f"{stem}.json", TRIALS_DIR / f"{stem}.md"
    json_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False) + "\n", "utf-8"
    )
    md_path.write_text(markdown(results), "utf-8")
    print(markdown(results))
    print(f"wall time {time.perf_counter() - started:.0f}s; {json_path}")
    if args.publish:
        WEB_FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
        (WEB_FIXTURES_DIR / f"{pack}.json").write_text(
            json_path.read_text("utf-8"), "utf-8"
        )
    if args.upload:
        upload([json_path, md_path])


if __name__ == "__main__":
    main()
