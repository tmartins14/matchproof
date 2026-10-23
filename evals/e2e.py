"""End to end: narrate_and_check on every beat of one golden match with the active judge.

uv run python -m evals.e2e            # red_card_flip seed 3, fan mode
"""

import argparse
import asyncio
import json
import re
import statistics
from collections import Counter
from datetime import date
from typing import Any

from agents.auditor import MAX_CONCURRENT_AUDITS, Auditor, summarize_audits
from agents.budget import MeteredClient, TokenBudget
from agents.llm_client import client_for
from agents.pipeline import Deps, run_beat
from intel.voice_lint import lint, numbers_in
from mcp_match import build_server

from .golden import build_store
from .run import REPORTS_DIR, percentile

TARGET_P90_MS = 8000
TARGET_NUMBERS_PER_FAN_CLAIM = 2.0
MACHINE_TOKEN = re.compile(
    r"\b(?:home|away)-\d{2}\b|\bev-\d{6}\b|\b[a-z]+_[a-z_]+\b", re.IGNORECASE
)


def readability(texts: list[str], beats: int, latencies: list[int]) -> dict[str, Any]:
    """How the published claims read: lint violations, numbers per claim, leaked machine tokens."""
    flagged = {t: [v.rule_id for v in lint(t, "narration")] for t in texts}
    return {
        "claims": len(texts),
        "claims_per_beat": round(len(texts) / beats, 2) if beats else 0.0,
        "claims_with_lint_violation": sum(1 for v in flagged.values() if v),
        "lint_violations": {t: v for t, v in flagged.items() if v},
        "numbers_per_claim": round(
            sum(len(numbers_in(t)) for t in texts) / len(texts), 2
        )
        if texts
        else 0.0,
        "machine_tokens_in_published_text": sum(
            len(MACHINE_TOKEN.findall(t)) for t in texts
        ),
        "beat_latency_p50_ms": round(statistics.median(latencies)),
        "beat_latency_p90_ms": percentile(latencies, 0.9),
    }


async def audit_claims(
    server: Any, match_id: str, checked: list[Any], client: Any = None
) -> dict[str, Any]:
    """The second model's check of every claim the Checker settled, as the live stream does it."""
    auditor = Auditor(client or client_for("auditor"), server)
    gate = asyncio.Semaphore(MAX_CONCURRENT_AUDITS)

    async def one(c: Any) -> tuple[Any, Any, str]:
        async with gate:
            return c.claim, await auditor.audit(match_id, c.claim), c.final.judge_reason

    rows = await asyncio.gather(
        *(one(c) for c in checked if c.claim.verdict.value in ("verified", "rephrased"))
    )
    return summarize_audits(match_id, rows)


async def main_async(story: str, seed: int, mode: str) -> dict[str, Any]:
    store, match_id = build_store(story, seed)
    server = build_server(store, writable=True)
    # A match's own counter, so the report has tokens and cost for this run only.
    counter = TokenBudget()
    deps = Deps(
        server,
        MeteredClient(client_for("narrator"), "narrator", counter=counter),
        MeteredClient(client_for("judge"), "judge", counter=counter),
    )
    runs = []
    for beat in store.beats(match_id):
        run = await run_beat(match_id, beat.id.root, mode, deps=deps)  # type: ignore[arg-type]
        runs.append((beat.id.root, run))
        print(
            beat.id.root,
            [c.verdict.value for c in run.claims],
            run.latency_ms,
            "ms",
            flush=True,
        )
    audit = await audit_claims(
        server,
        match_id,
        [c for _, r in runs for c in r.checked],
        MeteredClient(client_for("auditor"), "auditor", counter=counter),
    )
    spent = counter.snapshot()
    latencies = [r.latency_ms for _, r in runs]
    verdicts = Counter(c.verdict.value for _, r in runs for c in r.claims)
    chains = [
        {
            "beat_id": beat_id,
            "verdict": c.claim.verdict.value,
            "text": c.claim.text,
            "draft_text": c.claim.draft_text,
            "reason": c.claim.reason,
            "fact_ids": [f.root for f in c.claim.fact_ids],
            "first_check_reasons": c.first.reasons,
        }
        for beat_id, r in runs
        for c in r.checked
    ]
    return {
        "match_id": match_id,
        "mode": mode,
        "judge": deps.judge.deployment,
        "narrator": deps.narrator.deployment,
        "beats": len(runs),
        "claims": sum(verdicts.values()),
        "verdicts": dict(verdicts),
        "readability": readability(
            [c.text for _, r in runs for c in r.claims], len(runs), latencies
        ),
        "targets": {
            "machine_tokens": 0,
            "numbers_per_fan_claim": TARGET_NUMBERS_PER_FAN_CLAIM,
            "beat_latency_p90_ms": TARGET_P90_MS,
        },
        "tokens": {
            "narrator": sum(r.narrator_tokens for _, r in runs),
            "judge": sum(r.judge_tokens for _, r in runs),
        },
        "usage": spent["usage"],  # tokens in and out, by role
        "cost": spent["cost"],  # from config/prices.yaml, or "prices not set"
        "audit": audit,
        "chains": chains,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--story", default="red_card_flip")
    parser.add_argument("--seed", type=int, default=3)
    parser.add_argument("--modes", default="fan,analyst")
    args = parser.parse_args()
    for mode in args.modes.split(","):
        out = asyncio.run(main_async(args.story, args.seed, mode))
        name = f"{date.today().isoformat()}-e2e-{args.story}-{args.seed}-{mode}.json"
        path = REPORTS_DIR / name
        path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", "utf-8")
        print(
            json.dumps(
                {k: v for k, v in out.items() if k != "chains"},
                indent=2,
                ensure_ascii=False,
            )
        )
        for c in out["chains"]:
            print(f"[{c['verdict']}] {c['beat_id']}: {c['text']}")
        print(path)


if __name__ == "__main__":
    main()
