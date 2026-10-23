# Judge bake-off, 2026-10-22

Rule: at least 35 of 38 bad claims caught, at most 1 of 14 good claims blocked, judge p90 at most 4 s; highest catch count wins, then lower p90. Pick made by `evals/pick.py`.

| Judge | Bad caught (of 38) | by code | by judge | Good wrongly blocked (of 14) | Judge unavailable | p50 | p90 | Tokens per claim |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| judge-mai | 32 | 14 | 18 | 0 | 11 | 19.3 s | 25.3 s | 1634.3 |
| judge-grok | 38 | 14 | 24 | 0 | 1 | 7.8 s | 22.6 s | 959.3 |
| gpt-5-mini | 37 | 14 | 23 | 0 | 0 | 1.3 s | 1.7 s | 950.0 |

Winner: **gpt-5-mini**. no candidate met the rule, so the fallback judge is used: at least 35 of 38 bad claims caught, at most 1 of 14 good claims blocked, judge p90 at most 4 s; highest catch count wins, then lower p90.
No candidate qualified, so the fallback judge is active.

Bad claims are caught by code (reconciler or voice lint, no model call) or by the judge. Latency is the judge step's wall time per claim that reached the judge.
