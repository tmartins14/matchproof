# Build prompt 17 — Overnight re-run of grok-4.7 and phi-4-mini

**Mode:** code (small), then an unattended run. **When:** the last thing on Mon Oct 26, after prompt 16 has shipped and is deployed. **Budget:** 30 min of code, then the run overnight. **Branch:** `chore/trials-rerun`. **Depends on:** prompts 15 and 16 merged.

## Why

In the pack-v1 run:

- **grok-4.7** missed 68 of its 85 moments (`Narrator: LlmError`, p90 29.5 s against a 30 s timeout).
- **phi-4-mini** missed 23 (quota 20).

Both rows sit under "Incomplete run" on the Table. grok was also auditing every claim on the same `judge-grok` deployment, so it was competing with itself for capacity. Re-running both alone, one beat at a time, gives complete and honest rows by Tuesday morning.

This is a data refresh after the freeze. No app code changes; the web reads the new JSON on the next build.

## Do not touch

The web app, the API, scoring rules, the referee. The referee stays exactly as in pack-v1: same judge, same auditor deployment, same prompts. Changing it would make the merged rows incomparable with the rest.

## Part A — Code (30 min)

1. **Error causes.** `Narrator: LlmError` drops the cause. In `evals/trials.py`, record the cause name too (`LlmError.cause_name`, e.g. `APITimeoutError`, `RateLimitError`) in `reasons` and `errors` for `no_answer` rows. If the cause only lives inside the workflow's `_empty(...)` string, capture it with the existing observer or by catching it at the narrator client wrapper in `trials.py`. **Do not change `workflow.py`.**
2. **`--merge-into <results.json>`.** Run only `--candidates`, then in the target file:
   - replace those candidates' `claims`, `errors` and usage;
   - recompute every summary row and the ranking;
   - add this run's referee cost to `referee.cost` and record the merge as `{candidates, run_at, git_sha}` in a new `merges` array (schema, example, `make gen`).
   - Validate against the schema before writing.
   - Allow `--upload` and `--publish` with `--merge-into`.
3. **grok timeout.** In `models.yaml`, set the grok-4.7 trial candidate to `timeout_s: 60`.
4. **Separate narrator deployment for grok, if quick (≤10 min).** Create `narrator-grok` (same model and version as `judge-grok`) on `ais-oou4h3al` and point the grok-4.7 trial candidate at it, so the narrator and the auditor don't share capacity. If quota or anything else blocks it within 10 minutes, keep `judge-grok` and say so.
5. Tests: the merge replaces only the named candidates, recomputes ranks, adds cost and validates. The cause name appears on a `no_answer` row.

## Part B — Run (unattended, in order)

```
uv run python -m evals.trials --candidates grok-4.7 --parallel 1 --merge-into evals/reports/trials/pack-v1.json --publish
uv run python -m evals.trials --candidates phi-4-mini --parallel 1 --merge-into evals/reports/trials/pack-v1.json --publish
uv run python -m evals.trials_web evals/reports/trials/pack-v1.json
```

Set `MODEL_BASE_URL` (and `AZURE_STORAGE_ACCOUNT` if uploading) from `azd env get-value` for each command.

- **Stop conditions:**
  - stop if a single candidate is projected over 3 hours or US$10;
  - if grok still misses more than 10% of its moments with a 60 s timeout, let it finish anyway. It stays under "Incomplete run", now with real cause names, and that is the result.
- Commit and push after each merge, so a failure partway keeps what finished.
- Do **not** deploy. Tyler reviews the table in the morning, then deploys.

## Morning report (in the PR)

- **Before/after table:** all four rows from pack-v1, and after the merge.
- **Per candidate:** lost counts, and cause-name counts for every `no_answer`.
- **Wall time and cost** of each run.
- **Rank changes:** whether either model moved above the "Incomplete run" line or changed rank, and whether anything changed for gpt-5-mini (it shouldn't; it wasn't re-run).
- **Next step:** a one-line "deploy with `azd deploy web` after `npm run build`" for Tyler.
