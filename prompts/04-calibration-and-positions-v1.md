# Build prompt 04 — Calibration and positions v1

**Mode:** code. **Budget:** about 3 hours. **Branch:** `feat/calibration-positions-v1`. **Depends on:** prompt 03 merged.

## Context

Read `CLAUDE.md`, `docs/VOICE.md` (for any printed text), `docs/ARCHITECTURE.md` (Player positions), `docs/adr/0005-positions-contract-first.md`, `docs/adr/0007-absolute-pitch-coordinates.md`, `schemas/position_frame.schema.json`, `docs/compliance/DATA.md`, and `packages/sim/src/sim/engine.py`, especially its module docstring and the shape constants (`LINE_SHIFT`, `BALL_PULL`, `LATERAL_PULL`).

This task does two things:

1. Brings the generator inside realistic bands, with a calibration report the web app's calibration page will read later.
2. Adds version 1 of player positions: all 22 players at 5 Hz, plus a freeze frame for every event.

After this task, the pitch can be drawn and positional facts can be computed. Extractors come in prompt 05.

Two problems are already visible on `main`:
- **xG is too high.** Seed 1 of `late_comeback` totals 3.6 xG. The engine docstring says the high goal propensity is deliberate.
- **Possession swings too much.** With identical default tactics, seed 1 gives 53/47 and seed 2 gives 36/64. That range is too wide for two evenly set teams.

**Decision: realism wins over the demonstration setting.** Planted beats still guarantee the goals the storyline needs, and big chances still happen. A believable calibration page is worth more to the judges than extra organic shots.

Before writing: restate the task back in eight lines or fewer. Include:
- how engine and positions will share one shape model,
- how the actor gets pinned to the event location,
- how you will avoid a frame file that is too large.

Then wait for my go.

## Seam rules

- Pure, deterministic Python: `random.Random(seed)` only, no `numpy`, no wall-clock time.
- **One shape model.** The engine already uses slot anchors shifted by the ball and line height to pick players. Move that logic into `sim/shape.py`, and have both the engine and the position layer call it. The engine and the frames must never disagree about where a team's shape is.
- Changing generator constants changes every match. Re-run the prompt 03 tests, and say in the PR which constants moved and by how much.

## Part 1 — Calibration

1. **`packages/sim/calibration/targets.yaml`**: one entry per metric, with `id`, `per` (`team` or `match`), `band` `[lo, hi]`, `unit`, `source` and `status`.
   - **Starting bands, all `status: provisional`, `source: TBD`:**

     | Metric | Band |
     | --- | --- |
     | Passes per team | 380–650 |
     | Pass completion | 74–89% |
     | Mean pass length | 16–23 m |
     | Progressive pass share | 7–16% |
     | Shots per team | 7–20 |
     | xG per team | 0.4–2.8 |
     | xG per match | 1.5–3.8 |
     | xG per shot | 0.07–0.16 |
     | Possession share | 35–65% (default tactics, both teams equal) |
     | Fouls per team | 6–16 |
     | Yellow cards per team | 0–5 |
     | Corners per team | 2–10 |

   - Do not invent sources. The PR omissions list says these bands still need a cited source.
2. **`sim/calibrate.py`** and a CLI command, `uv run python -m sim calibrate --seeds 1-8 --out data/calibration.json`. It runs all four storylines on each seed with default tactics. It prints a table of metric, band, mean, min, max and pass/fail, and writes the same table as JSON with the run's seeds and git SHA (passed in; never read the clock).
3. **Tune engine constants** until every metric's **mean** across the 32 runs sits inside its band, and no single run is outside it by more than 15% of the band width. Lower the shot weight and the xG logistic first, and replace the "deliberately high" paragraph of the engine docstring with a short calibration note. For possession spread, look at how possession weights and turnovers interact. Keep a seed-to-seed spread; just narrow it.
4. **Test** `test_calibration.py`: the same rule as step 3, on seeds 1–4 to keep CI fast. Mark the 8-seed run `@pytest.mark.slow` and add it to a `make calibrate` target.

## Part 2 — Positions v1

1. **`sim/shape.py`**: the extracted shape model. Each player's target point comes from:
   - their formation slot anchor, in the team's attacking frame;
   - a shift for line height, applied in and out of possession (`LINE_SHIFT`);
   - a pull toward the ball, along the pitch (`BALL_PULL`) and across it (`LATERAL_PULL`);
   - **out of possession:** compress toward the ball. Add a named `COMPACT_OUT` constant, so the outfield area is smaller than in possession;
   - **in possession:** widen. Add a named `WIDTH_IN` constant;
   - **goalkeeper:** stays within 18 m of the goal line, tracking the ball laterally, damped.

   Clamp every point to the pitch.
2. **`sim/positions.py`**
   - `iter_frames(brief, events) -> Iterator[PositionFrame]`: one frame every 0.2 s of match clock, from kick-off to the end of the second period. Players move toward their shape target with a speed cap (`MAX_SPEED_V1 = 8.0` m/s) and report `speed_ms`. The ball moves along each event's path at a plausible speed. `role` is always `hold_slot`, as the schema says for version 1. `possession` comes from the current event.
   - **Pinning:** at each event's time, the event's actor is at the event location. For a pass, the recipient is at the end location by the time of the next event. Move only those players; everyone else keeps following the shape model.
   - **Freeze frames:** `freeze_frame(event) -> PositionFrame` with `freeze_frame_of` set to the event's id. Its `source_id` for facts is `ff-` plus the same six digits as the event, matching the existing `sourceId` pattern.
   - **Red cards:** a sent-off player leaves the frames at the card's time; frames then hold 21 (or 20) players.
   - `iter_stream(brief) -> Iterator[Event | PositionFrame]`: events and 5 Hz frames merged in time order. Wednesday's live stream uses this.
3. **Size:** round coordinates to 0.1 m and speeds to 0.1 m/s. The CLI's `generate` writes `<match_id>.frames.jsonl` (5 Hz) and `<match_id>.freeze.jsonl` next to the events. Report both file sizes in the PR. If a full match is over 25 MB of 5 Hz frames, say so and propose a fix (for example storing at 5 Hz but gzipping), rather than silently dropping the rate.

## Tests (`packages/sim/tests/test_positions.py`)

- Every frame validates against `position_frame.schema.json` (sample every 50th frame plus all freeze frames, to keep it fast).
- **Determinism:** the same brief gives byte-identical frame output.
- **Pinning:** every event's actor is within 1 m of the event location in its freeze frame (ADR 0005).
- **Speed:** no player's `speed_ms` is above the cap; no position jumps more than `cap × 0.2 s + 0.05 m` between frames, except the pinned actor at its event time (report how often that happens).
- Every point is on the pitch, frames are spaced 0.2 s apart, and the player count drops after a red card.
- **Dials move the shape:**
  - a team with `line_height` 0.85 has a mean back-line x (its deepest outfield player, measured toward its own goal, as FIFA defines line height) at least 8 m higher than the same team at 0.2;
  - out-of-possession outfield area (convex hull) is smaller than in-possession area for the same team.
- **The engine and positions agree:** `shape.py` is the only module that computes slot targets (a test greps for the constants outside it).
- **Speed of generation:** one full match with frames generates in under 4 seconds on a laptop.

## Conventions

- snake_case modules and functions; type hints everywhere; `mypy --strict` clean.
- Every tuned constant is a named module-level constant with a one-line comment.
- Printed text follows `docs/VOICE.md`.

## Verification signal (show the output)

1. `make lint typecheck test` exits 0; CI green.
2. `make calibrate` output (all 32 runs), before and after tuning.
3. The prompt 03 CLI summary for `late_comeback`, seeds 1 and 2, after tuning.
4. File sizes for one match's frames and freeze frames.
5. A PNG of three freeze frames from one match: a goal, a moment in a press, and a moment out of possession. Players plotted by team on a 120 × 80 pitch, any plotting library. Save it to `data/checks/freeze-frames-<match_id>.png`, which is ignored by git and never committed. Print its path at the end of your report. I will attach it to the PR description myself.

## Omissions list (required in the PR)

Unsourced calibration bands; constants chosen by feel; anything in the frames that looks wrong in the PNG and was not fixed.

## Out of scope

Extractors and facts (prompt 05), role-based movement (version 2, Mon Oct 26), the beat detector, SSE, any API or UI change, any Azure change.
