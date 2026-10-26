# Build prompt 14 — Narrator Trials: candidates as config, the pack runner, results JSON

**Mode:** code. **Budget:** about 3 hours (Part A 30 min, Parts B–D 2 h, Part E 30 min). **Branch:** `feat/narrator-trials`. **Depends on:** PR 34 merged. **Lands before:** prompt 15 (Table and Compare pages), which renders the JSON this task writes. **Replaces:** the old prompt 14 (cached replay); cached replay moves to the cut list.

## Why

Matchproof is repositioning as **Narrator Trials**: "You want an AI narrator? It has to pass this test first." Seeded matches with planted traps are the exam, a narrator model is the candidate, the Checker plus the Auditor are the fixed referee, and the output is a league table of models.

Nearly all of it exists. `evals/e2e.py` already plays every beat of a golden match through the workflow with a narrator, the inline judge and the auditor, and reports tokens, cost and latency. This task generalises it: many candidates, a fixed pack of six fixtures, one results file.

## Read first

- `CLAUDE.md` (seam rules: the summary and every score are computed here in Python; the browser only draws them)
- `evals/e2e.py`, `evals/golden.py`, `evals/run.py` (`REPORTS_DIR`, `percentile`)
- `packages/agents/src/agents/llm_client.py` (`client_for`, `settings_for`, `ModelSettings`)
- `packages/agents/config/models.yaml`, `packages/agents/config/prices.yaml`, `agents/prices.py`
- `packages/agents/src/agents/checker.py` (`Problem`, how `verified` / `rephrased` / `blocked` / `delayed` are decided, reason strings)
- `packages/agents/src/agents/reconcile.py` (reason strings), `auditor.py`, `consensus.py`, `budget.py`
- `packages/sim/src/sim/brief.py` (`STORYLINES`, `make_brief`, `validate_planted`, `PlantedSpec`)

## Do not touch

Generator, extractors, Checker rules, judge prompts, Auditor loop, consensus logic, the live stream, Composer, Blob archive, the Agent Framework workflow, CI workflows. The narrator prompt (`narrator.v2.md`) stays as it is: every candidate gets the same prompt. If a candidate needs a different setting, that goes in `models.yaml`, never in code.

## Part A — Candidate deployments (30 min, hard stop)

Target five candidates. The first two exist already.

| id | deployment | notes |
| --- | --- | --- |
| `gpt-5-mini` | `gpt-5-mini` | the incumbent |
| `grok-4.7` | `judge-grok` | also the auditor; flag it, do not drop it |
| `gpt-5-nano` | new | cheap same-vendor row, likely the Budget pick |
| `phi-4-mini` | new | Microsoft, catalog |
| `mistral-small` | new | catalog |

1. Deploy the three new models on Foundry resource `ais-oou4h3al` (rg `rg-matchproof-dev`) as Global Standard (serverless where that is the only option) with `az cognitiveservices account deployment create` or the portal. Record the exact model name and version.
2. Smoke each one through the existing client: one call with a `json_schema`, one with `json_object`, one with neither. Record which works, and whether `temperature` and `reasoning_effort` are accepted. Paste the results in the PR.
3. Any model that is not answering correctly within the 30 minutes is dropped. Say which and why. Do not retry Marketplace (Claude) deployments. Four candidates is fine; three is the floor.

## Part B — Candidates as config

1. Add to `models.yaml`:

   ```yaml
   # Narrator Trials: every candidate gets narrator.v2.md and the same referee.
   trial_candidates:
     - id: gpt-5-mini
       deployment: gpt-5-mini
       max_output_tokens: 700
       timeout_s: 20
       response_format: json_schema
       reasoning_effort: minimal
     - id: grok-4.7
       deployment: judge-grok
       ...
   ```

   Settings come from Part A's smoke results. `id` is what the Table shows.
2. Add `trial_settings(models, candidate_id) -> ModelSettings` and let `client_for("narrator", deployment=...)` take a candidate (today `deployment` only applies to the judge). Unknown candidate raises `LlmError("UnknownCandidate")`. Tests with the fake client.
3. Add prices for every new deployment to `prices.yaml` with `source` and `as_of`, same rules as PR 25: if a price cannot be sourced, leave it null and the report says "prices not set". Never guess.
4. A prompt hash: first 8 hex of the SHA-256 of the narrator prompt file as loaded. Put it on every row.

## Part C — The pack

`evals/trials/pack_v1.yaml`. All fixtures are Rivermouth v Ashford Vale (the default clubs), labelled by fixture id and seed. The generator can only plant `counter_goal`, `set_piece_goal`, `high_turnover_goal`, `open_play_goal`, `red_card` and `penalty`, so every trap is one of those or a consequence of them. No own goals, subs, disallowed goals or retaken penalties: the generator does not make them, and this task does not change the generator.

| id | seed | storyline | the trap |
| --- | --- | --- | --- |
| fx-01 | 101 | `red_card_flip` | red card ~60′, then two goals against ten men: player counts and which side is down to ten |
| fx-02 | 102 | `late_comeback` | away lead, home equaliser from a set piece, winner in 90′–95′: scoreline flips and a stoppage-time minute |
| fx-03 | 103 | `end_to_end` | six goals, 3–3, stoppage-time penalty: running score after each goal |
| fx-04 | 104 | `smash_and_grab` | home side has the ball, loses 0–1: overclaim from possession and territory |
| fx-05 | 105 | custom: `penalty` home 8–12, `red_card` away 20–25, `counter_goal` away 50–58 | early penalty plus a red card for the other side: attribution, who scored and who was sent off |
| fx-06 | 106 | custom: `open_play_goal` away 15–22, `counter_goal` away 33–40, `set_piece_goal` home 68–74, `high_turnover_goal` home 80–86, `open_play_goal` home 90–95 | 0–2 to 3–2: score and lead at every goal |

Each fixture has `id`, `seed`, `storyline`, optional `planted` list, a `brief` (one line in plain English, VOICE.md rules) and `traps` (`kind`, `note`). The trap **minute** is not written by hand: the runner reads it from the planted event in the generated match. Every custom `planted` list must pass `validate_planted`; a test asserts that. If one fails, move its window, do not change the validator.

Add `build_store_from_brief(brief)` to `evals/golden.py` (and have `build_store` call it) so a custom brief can be built the same way.

## Part D — The runner: `evals/trials.py`

```
uv run python -m evals.trials                      # pack-v1, every candidate
uv run python -m evals.trials --candidates gpt-5-mini --fixtures fx-01   # the smoke
uv run python -m evals.trials --no-audit           # skip the auditor, for a quick dry run
```

For each candidate × fixture:

1. Build the store for the fixture once per fixture, shared by candidates (a fresh store per candidate, built from the cached generation, so claims never mix).
2. Run every beat through `run_beat` exactly as `evals/e2e.py` does, mode `fan`, no Producer (every beat narrated). The narrator is the candidate. The inline judge is the active judge from `models.yaml` for every candidate, never the candidate.
3. Audit every settled claim with the auditor. Where the auditor disagrees, run `Consensus.review` with the inline judge and the candidate as the rewriter, as the live path does. The **scored verdict is what would be on air after consensus**.
4. Run candidates in parallel (one task per candidate, `--parallel` default 3), fixtures in sequence within a candidate. Keep `MAX_CONCURRENT_AUDITS`. Back off on 429 the way the auditor already does. A candidate that errors on a fixture gets the error recorded on that fixture and carries on; it is not silently dropped.

### Verdict mapping

| Checker verdict (after consensus) | Trials verdict | Pts |
| --- | --- | --- |
| `verified` | STANDS | +3 |
| `rephrased` | AMENDED | +1 |
| `blocked` | OVERTURNED | −3 |
| `delayed` | HELD | 0, unscored |

**One stamp per key moment.** Candidates may write one or two claims a beat, which would let a verbose model pile up points. Score only the first claim of each beat (lowest claim index). Record all claims; mark the scored one with `scored: true`. Beats are deterministic per fixture, so every candidate is scored on the same moments.

### Fail profile

`reason_bucket` comes from the first-check reasons of a claim that was not STANDS, by these rules, first match wins. No model is asked to classify anything.

| bucket | rule |
| --- | --- |
| `numbers` | reconcile: `The number "…" matches no display rendering` |
| `names` | reconcile: `The player "…" is not named` |
| `citation` | reconcile: `cites no facts` or `is not in the beat's fact bundle` |
| `attribution` | judge problem `wrong_entity` |
| `timing` | judge problem `wrong_time` |
| `overclaim` | judge problem `overclaim`, `motive`, `unsupported_cause` or `outside_knowledge`; also reconcile `compares, but no before or change fact` |
| `wording` | voice rule broken |
| `other` | anything else, with the raw reason kept |

Match on the judge's `problem` field and the reconciler's reason prefix, not on free text where a field exists. If a reason string needs a stable prefix to be matched, export it as a constant from the module that writes it rather than duplicating the string; that is the only change allowed in `reconcile.py` and `checker.py`.

### Output

`evals/reports/trials/pack-v1.json`, schema `schemas/trials_results.schema.json` (new; add an example under `schemas/examples/`, run `make gen` and `make check-contracts`). Shape, from the pivot handoff, with three additions marked:

```json
{
  "pack": "pack-v1", "run_at": "…Z", "git_sha": "c3e2a3a",                     // + git_sha
  "referee": {"checker": "code", "judge": "gpt-5-mini", "auditor": "judge-grok (grok-4.7)", "judge_prompt": "judge.v3.md"},
  "fixtures": [{"id": "fx-01", "seed": 101, "match_id": "m-red-card-flip-101", "home": "RIV", "away": "ASH",
                "brief": "…", "final_score": [2, 0], "traps": [{"minute": 60, "kind": "red_card", "note": "…", "event_id": "ev-…"}]}],
  "candidates": [{"id": "gpt-5-mini", "deployment": "gpt-5-mini", "model": "gpt-5-mini 2025-08-07", "prompt_hash": "ab12cd34",
                  "price_in": 0.25, "price_out": 2.0, "currency": "USD", "self_audited": false}],          // + self_audited
  "claims": [{"id": "cl-…", "fixture": "fx-01", "beat": "bt-…", "minute": 71, "candidate": "gpt-5-mini", "scored": true,
              "text": "…", "draft_text": "…", "verdict": "STANDS", "reason_bucket": null, "reasons": [],
              "failed_span": null, "corrected_span": null, "fact_ids": ["fx-…"],
              "checker": "4/4 numbers matched", "auditor": "agree", "corrected_by_consensus": false,
              "latency_ms": 1900, "tokens_in": 1800, "tokens_out": 90}],
  "errors": [{"candidate": "phi-4-mini", "fixture": "fx-03", "error": "LlmError(Timeout)"}],           // + errors
  "summary": [{"candidate": "gpt-5-mini", "claims": 66, "stands": 55, "amended": 7, "overturned": 3, "held": 1,
               "pts": 151, "clean_pct": 83.3, "p90_ms": 2100, "usd_per_match": 0.04, "tokens_per_match": 59000,
               "cleared": true, "fail_profile": {"numbers": 0.6, "wording": 0.4}, "form": ["S","S","A","S","S"],
               "by_fixture": {"fx-01": {"pts": 27, "clean_pct": 90.9}}}]
}
```

Rules for the summary, all computed here:

- counts and pts over **scored** claims only; `clean_pct = stands / (claims − held)`, one decimal;
- `cleared = overturned <= amended` ("Not cleared for air" when false);
- `p90_ms` over beat latencies; `usd_per_match` and `tokens_per_match` are the candidate's **narrator** usage only (the referee's cost is reported once, separately, under `referee.cost`), averaged over fixtures, from `prices.yaml` or "prices not set";
- `fail_profile` is the share of non-STANDS scored claims per bucket, summing to 1;
- `form` is the verdict of the last scored claim in each of the last five fixtures, S/A/O/H;
- `self_audited: true` for `grok-4.7` (the auditor's own model). The Table shows it as a footnote, the row stays.
- `failed_span` / `corrected_span`: for AMENDED claims, the shortest differing span between `draft_text` and `text` (word-level `difflib`), else null.
- Summary rows sorted by pts, then clean_pct, then p90_ms.

Also write a short `pack-v1.md` next to it: the table as Markdown, plus every OVERTURNED claim with its reason. That is what gets read on the train.

Upload both to Blob container `trials/` on `stoou4h3al` with the same managed-identity path the archive uses, behind `--upload`. Not uploaded by default.

Copy the JSON to `apps/web/fixtures/trials/pack-v1.json` (behind `--publish`), because the web build is a static export and prompt 15 imports it at build time.

## Part E — Run it

1. Unit tests: verdict mapping, scored-claim selection, bucket rules (one case per bucket using real reason strings), summary maths on a hand-built set of claims, `validate_planted` on both custom fixtures, `trial_settings` for a known and an unknown candidate.
2. Smoke: `--candidates gpt-5-mini,gpt-5-nano --fixtures fx-01`. Paste the Markdown table and wall time.
3. Then the full pack in the background with `--upload --publish`. Paste the Markdown table, the wall time, the total cost (candidates plus referee), and the error list. If the full run is not done when the PR is ready, open the PR with the smoke and say the full run is still going.

## Verification in the PR

- `make lint typecheck test check-contracts` output.
- Part A smoke table (model, version, which response formats work).
- Smoke and full-run Markdown tables, wall time, cost.
- Three sample claims per candidate (one STANDS, one AMENDED, one OVERTURNED where there is one) with fact ids, so a human can check the referee is right.

## Omissions to state

- Same narrator prompt for every candidate: a model tuned for a different prompt may score lower than it would with its own. That is the test, but say it.
- The inline judge is `gpt-5-mini`, which is also a candidate; the auditor is grok, also a candidate. Report agreement rates per candidate so self-favouring is visible.
- One run per candidate per fixture. No variance estimate.

## Stop conditions

- If a candidate's structured output fails on more than half its beats after the settings from Part A, drop it and say so; don't write a model-specific parser.
- If the full pack is projected over 90 minutes wall time or US$10, stop after the smoke and report the projection.
