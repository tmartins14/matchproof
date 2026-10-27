# Build prompt 19 — More narrators: a fixed shortlist, grok measured, a guaranteed Desk fallback

**Mode:** code, then unattended runs (overnight). **Branch:** `feat/more-narrators` from main. **Start:** after the UX round (feat/trials-ux-2) is merged and deployed. Never run both at once on this machine. **Authority:** merge and deploy, under the conditions in Part E.

## Why

Only gpt-5-mini is both cleared and measured, so the Desk has one narrator to choose from.

**Goal:** at least one more narrator ends both cleared and measured; two is the target. This prompt gives a fixed shortlist of the models most likely to pass, rather than an open search.

Don't re-run gpt-5-mini, gpt-5-nano or phi-4-mini: their numbers must not move.

## Read first

- `evals/trials.py`, `evals/trials_web.py`, `packages/agents/config/models.yaml` (`trial_candidates`), `packages/agents/config/prices.yaml`, `packages/agents/src/agents/llm_client.py`
- `prompts/14-narrator-trials-runner.md` Part A (how candidates were deployed and smoked)
- `prompts/17-overnight-rerun.md` (the `--merge-into` design, never built)

## Do not touch

The referee (Checker, judge, auditor, consensus, judge prompts), the narrator prompt, scoring, the generator, the pack, the existing candidates' results, the web components. The web changes only through the export.

## Part A — `--merge-into` (~30 min)

As designed in prompt 17 Part A2.

- Run only `--candidates`, then replace those candidates' `claims`, `errors` and usage in the target file. Recompute every summary row and the ranking.
- Add this run's referee cost to `referee.cost`, and append `{candidates, run_at, git_sha}` to a new `merges` array (schema, example, `make gen`).
- Validate against the schema before writing. Allow `--upload` and `--publish` with it.
- **Guard:** refuse to merge if the pack definition or the referee settings (judge, auditor, judge prompt) differ from the target file's.

Tests:
- only the named candidates change;
- ranks are recomputed;
- cost is added;
- the guard refuses a mismatched referee;
- the result validates.

## Part B — The shortlist (try in this order; stop adding once two count)

All are Azure OpenAI models sold directly by Azure, with structured outputs, deployed on `ais-oou4h3al` like gpt-5-nano was, with no Marketplace step. Use the exact names and versions `az cognitiveservices account list-models` reports for this resource. If a listed version isn't offered, use the nearest current version of the same model and say so.

| # | candidate id | model (version) | why it should pass | starting settings |
| --- | --- | --- | --- | --- |
| 1 | `gpt-5.4-mini` | gpt-5.4-mini (2026-03-17) | Newer sibling of gpt-5-mini; same call shape; fast and cheap | as gpt-5-mini: `json_schema`, `reasoning_effort: minimal`, default temperature, 700 tokens, 20 s |
| 2 | `gpt-4.1` | gpt-4.1 (2025-04-14) | Non-reasoning, strong at following instructions, fast; a different generation for the Table | `json_schema`, `temperature: 0`, no `reasoning_effort`, 700 tokens, 20 s |
| 3 | `gpt-5.4` | gpt-5.4 (2026-03-05) | The strong model: answers "would a better model fix this?" | `json_schema`, `reasoning_effort: minimal` (use `low` if minimal is rejected), 700 tokens, 30 s |
| 4 | `gpt-4.1-mini` | gpt-4.1-mini (2025-04-14) | Backup if 1–3 fall short | as gpt-4.1 |

**Don't try:** GPT-6 or 5.6 models (may need a quota request), `-pro`, `-codex` or `o`-series models (slow reasoning or wrong shape), gpt-4o-mini (JSON mode only), preview models (`gpt-chat-latest`, `gpt-oss`), or non-OpenAI vendors.

**For each model, in order:**
1. **Deploy** as Global Standard. If quota is short, use the largest capacity that fits.
2. **Smoke** as in prompt 14 Part A: the starting settings first; adjust only what a 400 or 422 error points at. 20-minute cap per model, deploy and smoke together; if it's not answering by then, skip it and say why.
3. **Config:** add it to `trial_candidates`, and add prices to `prices.yaml` with `source` and `as_of`. Leave a price null rather than guess.
4. **Run:** `uv run python -m evals.trials --candidates <id> --parallel 2 --merge-into evals/reports/trials/pack-v1.json`, with `MODEL_BASE_URL` from `azd env get-value`. You may run two shortlist models at once (`--candidates a,b`). Commit after each merge.
5. **Record** in `docs/realism/status.md`: model, smoke result, cleared, measured, counts toward the goal.

Once two models count, don't start more. A model that runs but ends uncleared stays on the Table: that's a result, not a failure of this prompt.

## Part C — grok-4.7, one fair run (after Part B's runs finish)

1. **Own deployment:** try to create `narrator-grok`, same model and version as `judge-grok`, at **capacity 30** (the free quota; capacity 50 failed). If it's created, point the grok-4.7 candidate at it.
   - If it's refused, including by a permission prompt, **don't retry**. Write the exact `az` command in `docs/realism/status.md` for Tyler, and keep `judge-grok`.
2. **Timeout:** grok-4.7 trial `timeout_s: 120`.
3. **Run once, alone:** `--candidates grok-4.7 --parallel 1 --merge-into …`. Commit after the merge.
4. If more than 10% of its moments are still unanswered, it stays unranked, with cause names. No further re-runs.

## Part D — Hero with several cleared narrators

`evals/trials_web.py` `hero`:

- **one** cleared and measured: unchanged;
- **two or more:** line 1 is "Cleared for air: <ids in rank order>." Line 2 is "Fewest traps fallen for: <id>, <o> of <n>. <worst measured uncleared id>: <o> of <n>, not cleared."

Tests for 0, 1 and 3 cleared.

## Part F — Guaranteed Desk fallback (only if no shortlist model counts by 6:00 AM ET)

The Desk selector also lists narrators that are **cleared but not measured**, clearly labelled.

- **Export:** Python writes `desk_candidates` with a `status` per entry (`ranked` | `incomplete`); the browser only renders it.
- **Label:** the option reads `<id> · INCOMPLETE RUN · CACHED`. The helper line reads "Incomplete runs replay what the model answered; unanswered moments show as NO ANSWER."
- **Replay:** unanswered beats appear as NO ANSWER (delayed) claims, so the gaps are visible.
- **Nothing else changes:**
  - it stays below "Not ranked" on the Table;
  - its row note stays;
  - it is never a pick;
  - `measured` stays false.
- **Tests:** cleared-unmeasured models appear only under this fallback; uncleared ones never appear.

## Part E — Export, checks, deploy

1. `uv run python -m evals.trials_web evals/reports/trials/pack-v1.json`. The recorded streams don't depend on candidates, so don't re-record. Then `npm run build`.
2. **Checks:**
   - the Desk NARRATOR select lists every model that counts (plus Part F entries if it applied);
   - picking a non-live one plays a `CACHED · pack-v1` replay with that model's claims;
   - the Table shows distinct live-feed and budget picks where the data says so;
   - Fixtures and Compare show the new columns and cards.
   - Run `npm test`, the e2e trials spec, and axe on the four pages.
3. **Deploy only if all hold:**
   - every candidate has 85 scored rows;
   - gpt-5-mini's summary row is unchanged from before this prompt;
   - the build passes;
   - the merge guard passed for every merge.

   Then `azd deploy web` and `scripts/smoke_prod.sh`. Otherwise **don't deploy**: the current site stays live. Report why.
4. **README:** regenerate the headline and candidate list from the export, plus Status and PROGRESS. Open a PR and merge it yourself when CI is green.

## Report (PR body)

- **Table:** before and after, all rows.
- **Per shortlist model:** model and version, smoke result, trap record, lost and cause counts, p90, $/match, cleared, measured.
- **grok:** measured or not, timeouts at 120 s, whether `narrator-grok` was created (or the command left for Tyler).
- **Fallback:** whether Part F applied.
- **Run:** wall time and cost.
- **Screenshots:** the Desk NARRATOR select open, and a cached replay of a new model at its first verdict.

## Stop rules

- Up to three attempts per failing step; then skip that model or step, record why in `docs/realism/status.md`, and continue.
- One model's failure never blocks the next.
- Never re-run gpt-5-mini, gpt-5-nano or phi-4-mini. Never change the referee or the pack.
- Keep `docs/realism/status.md` updated after each model and part, with the time and pass/fail.
