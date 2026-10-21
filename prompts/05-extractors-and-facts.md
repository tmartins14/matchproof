# Build prompt 05 — Extractors and the fact registry

**Mode:** code. **Budget:** about 3 hours. **Branch:** `feat/extractors`. **Depends on:** prompts 04 and 04.1 merged. 04.1 adds `sim/geometry.py`; the positional extractors here must import its functions instead of redefining back-line height, team length, width or hull area.

## Context

Read `CLAUDE.md`, `docs/VOICE.md`, `docs/ARCHITECTURE.md` (Pipeline, Player positions), `packages/sim/src/sim/geometry.py`, `schemas/fact.schema.json`, `schemas/common.schema.json` (the `sourceId` and `factId` patterns), `voice/examples.yaml`, and `packages/sim/src/sim/positions.py` (`freeze_source_id`, `iter_frames`, `iter_freeze_frames`).

Facts are the only numbers an agent may ever state. This task builds `packages/intel`: extractors that turn events and position frames into `Fact` objects, each carrying its display renderings and the sources it was computed from. No beats, no agents and no API yet; Wednesday's beat detector and Thursday's Checker are built on this.

`voice/examples.yaml` is the spec for what facts must exist. Every fact in it ("64% possession since the goal", "back line 26 m since", "8 Rivermouth players ahead of the ball", "3 v 1", "nearest defender 2 m at contact", "outfield area 540 m² since the red card", "ball won 31 m from goal") must be producible by some extractor.

Before writing: restate the task back in eight lines or fewer. Include:
- how fact ids stay stable and deterministic,
- how the batch and incremental paths are kept identical,
- which facts are precomputed and which are computed on demand.

Then wait for my go.

## Seam rules

- Pure, deterministic Python. No LLM calls, no network, no clock.
- Every fact has at least one source, and every source id exists: an event id in the events, an `ff-` id with a freeze frame, a `win-` id in the window table, or an `agg-` name registered by an extractor.
- Rounding and display live in one module. No extractor formats numbers itself.

## Schema change (first commit)

Add `m2` to the `unit` enum in `schemas/fact.schema.json`, for compactness areas. Run `make gen` in the same commit.

## Parts

1. **`intel/windows.py`:** fixed 15-minute windows of the match clock, `win-01` to `win-06`:
   - First half: 0–15, 15–30, then 30 to the end of the first half including stoppage.
   - Second half: the same three, with the last window running to the end of the second half including stoppage.

   `windows(events) -> list[Window]` with `id`, `period`, `t_from` and `t_to`.
2. **`intel/display.py`:** `render(value, unit, lang) -> list[str]`, the renderings the reconciler will accept. All renderings use digits.
   - **English:**
     - count: `"6"`
     - pct: 0.64 → `"64%"`, `"64 per cent"`
     - m: `"8 m"`, `"8 metres"`
     - m2: `"540 m²"`, `"540 square metres"`
     - s: `"11 seconds"`, `"11 s"`
     - xg: 0.41 → `"0.41 xG"`, `"0.4 xG"`
     - m_s: `"8.2 m/s"`
     - match minute: `"41′"`
   - **Spanish:** decimal comma (`"0,41 xG"`), `"64 %"`, `"8 m"`, `"11 segundos"`.
   - Rounding rules are named constants: percentages and metres to whole numbers, xG to 2 decimals plus a 1-decimal rendering.
3. **`intel/registry.py`:** `FactRegistry` with `add`, `get(fact_id)`, `by_name(name)` and `all()`.
   - Fact ids are derived from the name, deterministically: `fx-` plus a slug of the `metric(args)` name, matching `^fx-[a-z0-9_-]+$`. The same match always gives the same ids.
   - Adding the same name twice with a different value is an error.
4. **Event extractors (`intel/extract_events.py`):** per team, for the match, each period and each window:
   - passes, pass completion, shots, xG, possession share (completed-pass share, the same definition calibration uses), corners, fouls, cards;
   - **territory:** share of events in the opponent's half;
   - **field tilt:** share of final-third touches;
   - **high turnovers:** ball won within 40 m of the opponent's goal;
   - pressures in the opponent's third.

   **Sequence facts** for any possession that ends in a shot: seconds from regain to shot, passes in the sequence, and where the ball was won (metres from the opponent's goal). Sources are the event ids in the sequence.
5. **Positional extractors (`intel/extract_positions.py`).** From 5 Hz frames, sampled at 1 Hz to keep it fast (`SAMPLE_HZ = 1` as a named constant), per team per window, split in possession and out of possession:
   - **back-line height:** mean distance from the team's own goal line to its deepest outfield player, the FIFA definition;
   - **team length:** deepest to highest outfield player, along the pitch;
   - **team width;**
   - **compactness:** outfield convex-hull area, m²;
   - **distance between the defensive and midfield lines.**

   Sources: the window id plus an `agg-` name for the sampling.

   **From a freeze frame**, for any event, with source `ff-NNNNNN`:
   - attacking players ahead of the ball;
   - attackers versus defenders in the zone ahead of the ball, shown as `"3 v 1"` (zone depth is a named constant);
   - distance from the shooter to the nearest defender at a shot;
   - defenders between the ball and the goal.
6. **On-demand facts (`intel/since.py`):** `since(anchor_event_id, registry, events, frames)` computes "since X" facts (possession, shots, territory, back-line height, compactness) from the anchor to now. It also computes **change facts** between the 15 minutes before the anchor and the time since. For example:
   - `back_line_height(away, before ev-001589)` = 34 m,
   - `back_line_height(away, since ev-001589)` = 26 m,
   - `back_line_change(away, ev-001589)` = 8 m.

   A change fact's sources are the union of its parents' sources. These are not precomputed: the beat detector calls `since()` when a beat needs them, and the facts join the registry then.
7. **Batch and incremental:**
   - `extract_all(events, frames, freeze_frames) -> FactRegistry` runs everything.
   - `FactEngine.push(item)` takes events and frames in time order (the shape of `sim.iter_stream`) and returns the facts that changed, emitting window facts when each window closes.
   - At full time, the incremental registry must equal the batch registry exactly.
8. **CLI:** `uv run python -m intel facts --match data/matches/<match_id>` writes `<match_id>.facts.jsonl`, and prints counts by extractor plus ten sample facts with their display renderings.

## Tests (`packages/intel/tests/`)

- Every fact validates against `fact.schema.json`, and every source id exists in its match.
- **Determinism:** the same match gives byte-identical facts.
- **Batch equals incremental** at full time, on two storylines.
- **Known answers on hand-built inputs:**
  - a 4-event sequence with known pass lengths and completion;
  - a frame with outfielders on a 20 × 20 m square gives 400 m²;
  - a frame with the deepest outfielder 30 m from the goal line gives a 30 m back line, for both sides (ADR 0007 mirroring);
  - a shot frame with the nearest defender 2.0 m away gives 2 m.
- **Display:** each unit renders as specified in both languages; xG keeps two decimals.
- **Coverage of the examples:** a table maps each fact in `voice/examples.yaml` (except `ex-00`) to the extractor name that produces it. The test fails if any fact in the examples has no extractor. This keeps the Narrator's examples and the extractors in step.
- **Speed:** extracting all facts for one full match, frames included, takes under 6 seconds on a laptop. Mark it `slow` if CI timing is unreliable; prompt 04's 4-second test was flaky.

## Conventions

- snake_case modules and functions; type hints everywhere; `mypy --strict` clean.
- Every threshold and zone size is a named module-level constant with a one-line comment.
- Fact names follow `metric(args)`, e.g. `possession_share(home, win-04)` or `freeze_frame(ev-000597).attackers_ahead_of_ball`.

## Verification signal (show the output)

1. `make lint typecheck test` exits 0; CI green.
2. The CLI output for `red_card_flip` seed 3.
3. The `since()` output for that match's red-card event: back-line height before and after, and the change fact, with sources.
4. The coverage table from the examples test.

## Omissions list (required in the PR)

Unverified behaviour; thresholds chosen by feel (zone depth, high-turnover distance); and any example fact that could only be covered with a loose interpretation.

## Out of scope

The beat detector (Wednesday), the MCP server, SSE, agents, the reconciler, any UI, any Azure change, and retuning the shape model (prompt 04.1).
