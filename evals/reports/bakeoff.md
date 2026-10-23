# Judge bake-off, 2026-10-23

Rule: at least 41 of 44 bad claims caught, at most 1 of 18 good claims blocked, judge p90 at most 4 s; highest catch count wins, then lower p90. Pick made by `evals/pick.py`. Judge prompt: `judge.v3.md`.

| Judge | Bad caught (of 44) | by code | by judge | Good wrongly blocked (of 18) | Judge unavailable | p50 | p90 | Tokens per claim |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| judge-grok | 42 | 18 | 24 | 0 | 2 | 8.8 s | 22.5 s | 1339.5 |
| gpt-5-mini | 42 | 18 | 24 | 0 | 0 | 1.5 s | 2.1 s | 1365.5 |

Winner: **gpt-5-mini**. no candidate met the rule, so the fallback judge is used: at least 41 of 44 bad claims caught, at most 1 of 18 good claims blocked, judge p90 at most 4 s; highest catch count wins, then lower p90.
No candidate qualified, so the fallback judge is active.

Bad claims are caught by code (reconciler or voice lint, no model call) or by the judge. Latency is the judge step's wall time per claim that reached the judge.
