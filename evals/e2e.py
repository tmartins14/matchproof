"""End to end: narrate_and_check on every beat of one golden match with the active judge.

uv run python -m evals.e2e            # red_card_flip seed 3, fan mode
"""

import argparse
import asyncio
import json
import statistics
from collections import Counter
from datetime import date
from typing import Any

from agents.llm_client import client_for
from agents.pipeline import Deps, run_beat
from mcp_match import build_server

from .golden import build_store
from .run import REPORTS_DIR, percentile

TARGET_P90_MS = 8000


async def main_async(story: str, seed: int, mode: str) -> dict[str, Any]:
    store, match_id = build_store(story, seed)
    server = build_server(store, writable=True)
    deps = Deps(server, client_for("narrator"), client_for("judge"))
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
        "beat_latency_p50_ms": round(statistics.median(latencies)),
        "beat_latency_p90_ms": percentile(latencies, 0.9),
        "target_p90_ms": TARGET_P90_MS,
        "tokens": {
            "narrator": sum(r.narrator_tokens for _, r in runs),
            "judge": sum(r.judge_tokens for _, r in runs),
        },
        "chains": chains,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--story", default="red_card_flip")
    parser.add_argument("--seed", type=int, default=3)
    parser.add_argument("--mode", default="fan")
    args = parser.parse_args()
    out = asyncio.run(main_async(args.story, args.seed, args.mode))
    path = REPORTS_DIR / f"{date.today().isoformat()}-e2e-{args.story}-{args.seed}.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", "utf-8")
    print({k: v for k, v in out.items() if k != "chains"})
    print(path)


if __name__ == "__main__":
    main()
