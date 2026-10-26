# Build prompt 18 — Offside-correct positions (B), then realistic play with the offside rule (C)

**Mode:** code, then unattended runs. **Owner:** Claude Code, working alone. Tyler checks in now and then; don't wait for him unless a stop condition below says so.

| part | branch | merge | deploy |
| --- | --- | --- | --- |
| **B** | `feat/offside-positions` | yes, by you, when its gates pass | yes, by you, when its data refresh passes |
| **C** | `feat/realistic-play` | **no**: Tyler reviews Tue morning | **no** |

**Clock (ET):**
- **B** merged by ~4:45 PM and deployed with fresh data by ~7 PM (feature freeze is 8 PM).
- **C** core green by **9:00 PM**. After 9:00 PM, **any** failure ends C: stop, report, leave the branch.
- If C hasn't landed by Tue 8 AM, it's dropped and B ships.

## Why

A football-literate viewer spots attackers standing offside within seconds of watching a match. That costs credibility on a Premier League panel.

- **B** fixes what's on screen without changing the match.
- **C** makes the match itself play more realistically, with the offside rule enforced in play.

## Read first

- `CLAUDE.md`: seam rules, conventions, "if a correction fails twice, stop" (overridden below for the unattended parts: see Stop rules).
- `packages/sim/src/sim/engine.py`: the possession-chain engine. `_choose_recipient`, `_pass`, `_pos_rel`, the `_seq_*` planted sequences and `_schedule`.
- `packages/sim/src/sim/positions.py`: the 5 Hz position layer. It is built **from** events (`iter_frames(brief, events)`); events never read it.
- `packages/sim/src/sim/shape.py`: shared by both, so treat any change to it as a C change, not a B change.
- `packages/sim/src/sim/calibrate.py`, `packages/sim/calibration/targets.yaml`, `packages/sim/tests/test_calibration.py`
- `packages/intel/tests/matches.py`: the on-disk generation cache (`.cache/matches`).
- `evals/trials.py`, `evals/trials_web.py`, `scripts/record_fixtures.py`, `evals/trials/pack_v1.yaml`
- `prompts/17-overnight-rerun.md`: its grok and error-cause fixes are folded into Part B3 below; 17 itself is not run.

## Do not touch (both parts)

The Checker, judge, auditor and consensus; narrator and judge prompts; the API and the live stream; the web app's components. The web only changes through regenerated data and the trap-label item in B4.

---

## Part B — Offside-correct positions (~2 h code, then the data refresh)

### B1. Measure first

Add `sim/realism.py` with pure, tested functions over events and frames:

- `offside_at_pass(frames, events)`: for every completed or attempted forward pass, is the intended receiver beyond **both** the ball and the second-last defender, in the opponents' half, at the frame nearest the pass? Use the standard rule; level counts as onside.
- `max_speed`, `max_accel`: per player, from consecutive 5 Hz frames.
- `teammate_overlap`: share of frames with two teammates closer than 1.5 m.
- `line_coherence`: the spread in x of each back line, out of possession.

Run it over the six pack fixtures plus calibration seeds 1–8 and save `docs/realism/baseline.json`. Paste the table in the PR.

### B2. Fix, in `positions.py` only

- At the moment of every pass, an attacking player without the ball is placed level with or behind the second-last defender (or behind the ball, if that's further forward). The receiver of a through ball then runs onto it, arriving at the event's end location by the event time.
- Movement stays within realistic limits: about 9.5 m/s top speed and about 6 m/s² acceleration. Tune within reason, state the values, and use them in the realism checks.
- Don't touch `shape.py` or `engine.py`. If the fix seems to need them, it belongs in C. Note it and do what you can in `positions.py`.

### B3. Gates. All must pass before merge.

1. **Same events:** for all six pack fixtures and calibration seeds 1–8, the SHA-256 of the events stream is identical before and after. If not, revert B2 and stop B.
2. **Same beats:** beat ids per pack fixture are identical before and after. If not, revert and stop B.
3. **Realism:** `offside_at_pass` ≤ 1% of forward passes (it was the baseline before); speed and acceleration within the stated caps; no worse `teammate_overlap`.
4. **Calibration:** `make calibrate` passes (the shape metrics in particular: `back_line_height_*`, `team_length_out`, `team_width_out`, `compactness_out`).
5. **Fixtures regenerated:** clear `.cache/matches`, then regenerate the desk fixtures and the recorded test stream (`scripts/make_desk_fixture.py`, `scripts/record_stream.py`, the setup and metric-family scripts). Byte-comparison test failures from the new positions are expected; update those fixtures, don't loosen the tests.
6. **Checks:** `make lint typecheck check-contracts`, `uv run pytest -n 2 --dist loadfile -m "not slow"`, `uv run pytest -m slow -k calibration`, and `cd apps/web && npm test`.

Then open a PR with before/after realism tables and two freeze-frame screenshots, one before and one after, at a pass that was offside in the baseline. Merge it yourself once CI is green.

### B4. Data refresh on main (unattended, ~90 min)

Position facts (compactness, distance between lines) change with B, so the pack is re-run on the new positions, including prompt 17's grok fixes.

1. **Grok fixes from prompt 17:**
   - record `LlmError.cause_name` on `no_answer` rows;
   - grok-4.7 trial `timeout_s: 60`;
   - try a separate `narrator-grok` deployment (same model and version as `judge-grok`), **10-minute cap**, and if it works point the grok candidate at it. If it doesn't, keep `judge-grok` and say so.
2. **Trap labels:** in `evals/trials_web.py`, add `label` to each trap from its `kind` and `note`, for example `RED CARD 61′`, `STOPPAGE-TIME PENALTY 90+8′`, `LATE WINNER 90+7′`, `OFFSIDE 38′`. Put the label map in Python with a test. The Fixtures page and the Desk trap chips show `label` in place of `TRAP <clock>`; that's the only web-component change allowed in this prompt.
3. **Full pack run:** `uv run python -m evals.trials --parallel 2 --upload --publish` with `MODEL_BASE_URL` and `AZURE_STORAGE_ACCOUNT` from `azd env get-value`. Upload may still fail on permissions; that's not a blocker.
4. **Regenerate:** `uv run python -m evals.trials_web evals/reports/trials/pack-v1.json`, then `uv run python -m scripts.record_fixtures`, then `npm run build`.
5. **Deploy only if all of these hold:**
   - every candidate has 85 scored rows;
   - gpt-5-mini is still both measured and cleared;
   - the build passes;
   - the six recordings' beat ids match the export.

   If they hold: `azd deploy web`, then `scripts/smoke_prod.sh`.

   If not, **don't deploy**: the current site stays live, and you report why.
6. **README:** regenerate the headline numbers (trap record, ranks) from the new export, plus Status and PROGRESS. Open a PR, and merge it yourself once CI is green.

**Report B:** old vs new Table (all rows), the trap record per model, lost and cause-name counts, the deployed URL, smoke output. Say plainly if any headline number moved, for example gpt-5-mini's 0 of 14.

---

## Part C — Realistic play with the offside rule (branch only; no merge, no deploy)

Start once B is merged. You can start C's code while B4's pack run is going, but keep tests at `-n 2` and don't run the slow calibration suite at the same time as the pack.

### Scope

**In scope:**
- realistic open play, including **players obeying the offside rule**: attacking teams time their runs, defences hold a line, and an offside pass is called (flag, offside free kick to the defending side);
- **one new trap type, `offside_flag`:** a planted move where a dangerous through ball is flagged offside. No shot, no goal. The trap is a narrator calling it a chance, a shot or a goal.

**Out of scope:** substitutions, own goals, disallowed goals or VAR, injuries, new set-piece types. Don't build any of these, even partly.

### C1. Engine (`engine.py`, `shape.py`, `positions.py`)

- **Defensive line:** the back line holds a coherent line height that follows the ball and the phase of play, steps up after clearances, and drops when the ball carrier faces goal without pressure. Use and extend `shape.py`.
- **Runs:** attackers time runs off the last defender; a through ball goes to a runner who was onside when it was played.
- **Offside call:** when the chosen pass would go to an offside player, either the passer picks someone else (most of the time) or the pass is played and flagged. A flag emits an offside event (the StatsBomb-style "Offside" type, or a pass with an offside outcome; follow the existing event schema's conventions, extend `schemas/event.schema.json` if needed, then run `make gen`) and an indirect free kick to the defenders from the offside position.
- **Positions and engine agree:** `offside_at_pass` ≈ 0 for unflagged passes, and = 1 for flagged ones.
- **Planted moments still land:** every existing planted kind still happens inside its window. `validate_planted` and the generator's planted-moment tests pass on seeds 1–200.
- **`offside_flag` planted kind:**
  - add it to the `match_brief` schema enum, `_seq_offside_flag` in the engine, `_words`/`custom_text`, and `validate_planted` (it's not a goal; window rules as for `red_card`);
  - extractors already turn events into facts. If an offside event yields no fact, add the minimal event fact (who was flagged, minute, side) in the extractor that handles that event type, with provenance, and say so. That's the only extractor change allowed.

### C2. Realism and calibration gates

1. **Calibration:** `make calibrate` passes on seeds 1–8 for all storylines. Add a target `offsides_per_match` with band `[1, 6]` (source: typical top-flight average of about 3–4 per match; mark it `status: estimate` with that note).
2. **Realism:** `offside_at_pass` ≤ 1% of unflagged forward passes; speed and acceleration caps from B hold; `line_coherence` improves on the B baseline; `teammate_overlap` no worse.
3. **Planted moments:** every pack fixture's planted moments land; `validate_planted` passes on every custom fixture.
4. **Checks:** `make lint typecheck check-contracts`, `uv run pytest -n 2 --dist loadfile -m "not slow"`, `cd apps/web && npm test`.

**9:00 PM checkpoint:** commit, push, and write `docs/realism/c-status.md` (gates passing and failing, numbers). If any gate is failing at 9:00 PM, **stop C** and report. From 9:00 PM on, any failure is final: no further fix attempts.

### C3. Pack on C (only if C2 passed by 9:00 PM)

1. **Pack:** in `evals/trials/pack_v1.yaml`, add an `offside_flag` planted moment to **fx-05** (home side, window 35–42) with the trap note "Flagged offside: not a chance, not a shot." Validate the pack.
2. **Regenerate on the branch:** clear `.cache/matches`, run the full pack (`--parallel 2`, no `--upload`, `--publish` to the branch's web fixtures), then `trials_web`, `record_fixtures` and `npm run build`. Matches, beat ids and trap minutes all change; everything downstream is data-driven.
3. **Check the joins:**
   - recorded beat ids match the export;
   - every trap resolves to a beat;
   - the Compare static params build;
   - the e2e trials spec passes against `out/`.
4. **Report** (PR, not merged):
   - the realism table: baseline, then B, then C;
   - the calibration table;
   - the new Table and trap record next to B's;
   - screenshots of a C freeze frame at a flagged offside and of the fx-05 offside trap on Compare;
   - wall time and cost.

---

## Stop rules (override "fix twice then stop" for unattended work)

- **Before 9:00 PM:** up to **three** attempts at any one failing gate, each with a different approach written down in the PR. After the third, stop that part and report.
- **After 9:00 PM:** C stops at the first failure. B4's run and deploy may still finish if they started before 9:00 PM.
- **Never:**
  - merge or deploy C;
  - delete or rewrite pack-v1 results on `main` outside B4;
  - change the referee, the scoring or the narrator prompt;
  - run `pytest -n auto`.
- **If the machine runs low on memory,** stop the test runs, never the pack run.
- **Keep `docs/realism/status.md` up to date** after each gate (B1…B4, C1…C3), with the time and pass/fail. That's what Tyler reads when he checks in.
