# Judge bake-off, 2026-10-22

Rule: at least 28 of 30 bad claims caught, at most 1 of 10 good claims blocked, judge p90 at most 4 s; highest catch count wins, then lower p90. Pick made by `evals/pick.py`.

| Judge | Bad caught (of 30) | by code | by judge | Good wrongly blocked (of 10) | Judge unavailable | p50 | p90 | Tokens per claim |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| judge-mai | 25 | 13 | 12 | 0 | 12 | 22.5 s | 25.0 s | 1310.3 |
| judge-grok | 13 | 13 | 0 | 0 | 27 | 0.3 s | 30.3 s | 0.0 |
| gpt-5-mini | 29 | 13 | 16 | 0 | 0 | 1.7 s | 2.1 s | 658.0 |

Winner: **gpt-5-mini**. no candidate met the rule, so the fallback judge is used: at least 28 of 30 bad claims caught, at most 1 of 10 good claims blocked, judge p90 at most 4 s; highest catch count wins, then lower p90.
No candidate qualified, so the fallback judge is active.

Bad claims are caught by code (reconciler or voice lint, no model call) or by the judge. Latency is the judge step's wall time per claim that reached the judge.
