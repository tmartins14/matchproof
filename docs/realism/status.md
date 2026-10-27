# Realism status (prompt 18, Part B only)

Part C is out of scope for this run: no `feat/realistic-play`, no `engine.py` / `shape.py` changes.

| gate | time (ET) | result |
| --- | --- | --- |
| B1 measure | 14:45 | pass: `sim/realism.py`, `docs/realism/baseline.json` |
| B2 fix (`positions.py` only) | 15:55 | done; numbers below |
| B3.1 same events | 15:55 | pass: SHA-256 of the events stream identical for the 6 pack fixtures and calibration seeds 1-8 x 4 storylines (38 matches) |
| B3.2 same beats | 15:58 | pass: beat ids identical for fx-01 to fx-06 |
| B3.3 realism | 15:55 | pass: offside 0.60% of forward passes (limit 1%), speed 9.43 m/s (9.5), acceleration 5.73 m/s² (6.0), teammate overlap 0.526% (was 0.646%) |
| B3.4 calibration | 16:00 | pass: `pytest -m slow -k calibration` and `sim calibrate --seeds 1-8` (every row, shape rows included) |
| B3.5 fixtures | 16:04 | regenerated: `stream-short`, `metric-families`, six `public/trials/streams`; `desk.json` and `setup.json` unchanged; adv-42's quoted compactness 730 -> 755 |
| B3.6 checks | 16:17 | pass: lint, typecheck, check-contracts, `pytest -n 2 -m "not slow"` (646 passed, 1 xfailed), `npm test` (80 passed) |
| B merged | 16:32 | PR 39 merged by me after CI green (13 min) |
| B4.1 grok fixes, B4.2 trap labels | 16:48 | PR 40 merged: cause names on `no_answer` rows, grok-4.7 `timeout_s: 60`, trap `label`. `narrator-grok` not created: `InsufficientQuota` at capacity 50 (30 units free) and the retry at 30 was refused by the permission classifier; grok keeps `judge-grok` |
| B4.3 full pack run | 16:33 to 18:17 | done (6253 s, referee cost 0.94 USD). `--upload` failed with 403 `AuthorizationPermissionMismatch` (not a blocker); `--publish` wrote the web copy |
| B4.4 regenerate | 18:19 | `trials_web`, `record_fixtures`, `npm run build` ok |
| B4.5 deploy | 18:21 | all four conditions held (85 scored rows each; gpt-5-mini measured and cleared; build passes; recorded beat ids match the export). `azd deploy web` done, `scripts/smoke_prod.sh` 5 of 5 ok |
| B4.6 README | 18:30 | README headline, limits, Status and PROGRESS updated; PR open |

## Realism, before and after (6 pack fixtures + calibration seeds 1-8 x 4 storylines)

| measure | before | after |
| --- | --- | --- |
| forward passes judged | 7878 | 7878 |
| offside at the pass (share of forward passes) | 9.39% | 0.60% |
| max speed, m/s (cap 9.5) | 7.91 | 9.43 |
| max acceleration, m/s² (cap 6.0) | 24.82 | 5.73 |
| teammate overlap (share of frames) | 0.646% | 0.526% |
| back-line spread, m (lower is tighter) | 1.48 | 1.78 |
| pinned-actor placements over one step's run | 1050 | 3690 |

Values (all in `positions.py`): speed cap 9.5 m/s reported (8.8 m/s inside, for 0.1 m rounding), acceleration 5.0 m/s²
(measured over 0.6 s windows, at most 5.73), offside margin 0.8 m, teammate separation nudge under 3.5 m.

Assumptions and costs:
- Speed and acceleration are measured on running. An event actor is still placed on its event location (ADR 0005), which is a placement, not a step; those are counted separately (`snap_jumps`). They rose from 1050 to 3690 over 24.1 M player steps (0.004% to 0.015%, the existing test allows 0.1%) because capped acceleration reaches fewer of the engine's event locations in time. Removing them needs the engine to place events where a player can be, which is Part C.
- Back-line spread rose from 1.48 m to 1.78 m. Not a B gate (it is C's), reported for the record.

# More narrators (prompt 19)

Shortlist deployed on `ais-oou4h3al` as Global Standard, capacity 50 each. Versions as `az cognitiveservices account list-models` reports them.

| gate | time (ET) | result |
| --- | --- | --- |
| A `--merge-into` | 22:15 | done: `evals/trials.py`, `merges` in the results schema and example, 5 tests (only named candidates change, ranks recomputed, cost added, referee and pack guards refuse, result validates) |
| D hero with several cleared | 22:40 | done: `hero` now carries `cleared` (rank order), `sole`, `fewest`, `worst`; tests for 0, 1 and 3 cleared |
| B1 gpt-5.4-mini (2026-03-17) | 22:30 | smoke pass with the starting settings (json_schema, reasoning_effort minimal; 3.2 s) |
| B2 gpt-4.1 (2025-04-14) | 22:34 | smoke pass with the starting settings (json_schema, temperature 0; 2.6 s) |
| B1 gpt-5.4-mini run | 22:36 to 23:15 | merged (with gpt-4.1, 2332 s together): 169 pts, 0 of 14 traps overturned (3 amended), 1 lost (1 rejected), p90 1.9 s, $0.0483 a match; cleared and measured; counts |
| B2 gpt-4.1 run | 22:36 to 23:15 | merged: 217 pts, 0 of 14 traps overturned, 0 lost, p90 2.8 s, $0.0804 a match; cleared and measured; counts |
| goal | 23:15 | two models count; gpt-5.4 and gpt-4.1-mini not started, as the prompt says |
| C1 narrator-grok | 23:16 | created at capacity 30 (Succeeded); smoke 5.7 s; `auditor_model` added to `models.yaml` so the Trials label and the self-audited flag stay `judge-grok (grok-4.7)` and true |
| C3 grok run | 23:18 to 00:41 | first attempt crashed before any call (a `model` key in the auditor config); second merged (4937 s): 246 pts, 0 of 14 traps overturned, 1 unanswered (`APITimeoutError` at 120 s), p90 70.2 s, $0.0697 a match; cleared and measured |
| F fallback | n/a | not needed: three shortlist models count |
| E export, checks, deploy | 00:30 to 00:44 | export regenerated; gpt-5-mini, gpt-5-nano and phi-4-mini rows and claims identical to before the prompt; every candidate has 85 scored rows; merge guard passed for both merges; vitest 81, e2e trials 14, axe on four pages clean; `azd deploy web` and `scripts/smoke_prod.sh` 5 of 5 |
