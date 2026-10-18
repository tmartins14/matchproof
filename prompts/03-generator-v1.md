# Build prompt 03 — Match generator v1 (events)

**Mode:** code. **Budget:** about 3 hours. **Branch:** `feat/generator-v1`. **Depends on:** prompts 01 and 02 merged.

## Context

Read `CLAUDE.md`, `docs/ARCHITECTURE.md` (Pipeline, Tactics and the brief), `docs/adr/0004-tactics-canonical-input.md`, `docs/adr/0007-absolute-pitch-coordinates.md`, and `schemas/match_brief.schema.json` and `schemas/event.schema.json`. The Pydantic models you will use are already generated in `packages/contracts/src/contracts/models.py`: `MatchBrief`, `Team`, `Player1` (a roster entry), `Storyline`, `PlantedBeat`, `Event`, `Pass`, `Shot`, `Pressure`. Do not edit that file; if a schema must change, change the schema and run `make gen` in the same PR, and say why in the PR.

This task builds the first version of the synthetic match generator in `packages/sim`: tactics in, a full match of events out, deterministic per seed, with the brief's planted beats guaranteed to happen. No player positions yet (that is Tuesday), no calibration against real data yet (also Tuesday), no API.

Before writing: restate the task back in eight lines or fewer, including how you will make planted goals happen and keep the final score consistent with the storyline. Wait for my go.

## Seam rules

- This is pure, deterministic Python. Use `random.Random(seed)` only; no global random state, no `numpy`, no wall-clock time.
- The generator emits events only. It computes no statistics for display; tests may compute summary numbers to check plausibility.

## Part 0 — Housekeeping (separate commit, first)

- `git rm --cached .DS_Store` (it is still committed at the root).
- In `docs/adr/0002-foundry-and-agent-framework.md`, append to the Decision log: on 2026-10-18 a quota request was filed for **Claude Sonnet 4.6, Global Standard, Hosted on Anthropic infrastructure, 80K TPM**; if approved, the Checker's judge moves to Claude so the Narrator and judge are different models; the existing line about Sonnet 5.5 stays as the alternative.

## Parts

1. **`sim/tactics.py`**
   - `FORMATIONS: dict[str, list[tuple[float, float]]]`: 11 slot anchors per formation for a team attacking toward x = 120, slot 0 the goalkeeper. Copy these exactly; positions v1 reuses them on Tuesday:
     ```
     "4-3-3":   (6,40) (26,12) (24,30) (24,50) (26,68) (45,40) (52,24) (52,56) (76,14) (80,40) (76,66)
     "4-2-3-1": (6,40) (26,12) (24,30) (24,50) (26,68) (42,32) (42,48) (60,40) (66,16) (66,64) (80,40)
     "4-4-2":   (6,40) (26,12) (24,30) (24,50) (26,68) (46,14) (44,32) (44,48) (46,66) (70,34) (70,46)
     "3-5-2":   (6,40) (24,22) (22,40) (24,58) (48,8) (44,30) (40,40) (44,50) (48,72) (72,34) (72,46)
     "5-3-2":   (6,40) (30,8) (22,24) (20,40) (22,56) (30,72) (44,26) (42,40) (44,54) (68,34) (68,46)
     ```
   - `slot_anchor(formation, slot, side) -> tuple[float, float]`: away mirrors x to `120 - x`.
   - `role_of(formation, slot) -> Literal["gk", "def", "mid", "att"]`, derived from the formation string.
2. **`sim/roster.py`**: `make_roster(side, seed) -> list[Player1]` producing 11 fictional players (ids `home-01`… / `away-01`…, slots 0–10, shirt numbers, `pace` 7.0–9.6 m/s, goalkeeper slowest). Names from a fixed in-repo list of at least 40 fictional surnames; never real Premier League players. Deterministic per seed and side.
3. **`sim/brief.py`**
   - `STORYLINES`: the four storyline ids in the schema, each with its English text and its planted beats:
     | id | text | planted beats (kind, side, minute window) | final score (home–away) |
     | --- | --- | --- | --- |
     | `late_comeback` | Ashford score first on the break; Rivermouth equalise from a set piece and win it late. | counter_goal away 35–45; set_piece_goal home 75–85; high_turnover_goal home 90–95 | 2–1 |
     | `red_card_flip` | A goalless first half, then a red card on the hour flips the game. | red_card away 58–62; open_play_goal home 65–75; open_play_goal home 80–88 | 2–0 |
     | `smash_and_grab` | Rivermouth dominate the ball but lose 1–0 to a single counter. | counter_goal away 60–75 | 0–1 |
     | `end_to_end` | End to end, 3–3, with an equaliser in stoppage time. | open_play_goal home 10–20; counter_goal away 25–35; set_piece_goal home 40–45; open_play_goal away 55–65; high_turnover_goal home 70–80; penalty away 91–95 | 3–3 |
   - `make_brief(home: TeamTactics, away: TeamTactics, storyline_id, seed) -> MatchBrief`, where `TeamTactics` is a small dataclass of name, short code, formation, press, directness and line height. Defaults: Rivermouth (`RIV`) at home, Ashford Vale (`ASH`) away. `match_id` is `m-<storyline>-<seed>` with underscores turned into hyphens.
   - `brief_text(brief) -> str`: the deterministic tactics-to-brief template, word for word as in the prototype (`teamLine` in `docs/prototype/Main.dc.html`, English only for now): bands press ≥ 0.7 / ≥ 0.45, directness ≥ 0.65 / ≥ 0.35, line ≥ 0.65 / ≥ 0.4.
4. **`sim/engine.py`**: a possession-chain state machine.
   - Clock: period 1 runs 0 to 45 minutes plus 1–4 minutes of stoppage; period 2 runs 45 to 90 minutes plus 2–6, both drawn from the seed. Emit `period_start`, a `kick_off`, and `period_end` markers. `t` is seconds and never decreases. Each event type advances the clock by a type-specific random interval, tuned so a match lands around 2,500 events.
   - Each step picks an actor from the team in possession (weighted by role and by where the ball is relative to that player's slot anchor) and an action: pass, carry, shot; the defending team may insert pressure, then tackle, interception, duel or foul.
   - **Dials drive behaviour.** `directness` raises pass length and forward angle and lowers completion. The opponent's `press` raises pressure frequency and the chance of a turnover high up the pitch. `line_height` moves where a team wins the ball back. Keep each effect a short, named, commented formula.
   - Shots happen mostly in the final third. Shot `xg` comes from a simple logistic on distance and angle to the goal centre (headers lower); clamp 0.01–0.9.
   - **Scoring rule for v1:** only planted beats score. Organic shots that would score are recorded as saved, wide, blocked or post, so the final score always matches the storyline. Note this in a module docstring as a v1 simplification.
   - **Planted beats.** At a random time inside each window, inject a short scripted sequence and tag every event in it with `planted_beat_id`:
     - `counter_goal`: interception in own half → carry → one or two passes → shot, goal; 8 to 14 seconds end to end.
     - `set_piece_goal`: corner → header shot, goal.
     - `high_turnover_goal`: pressure → interception within 40 m of the opponent's goal → pass → shot, goal.
     - `open_play_goal`: three to six completed passes ending in a shot, goal.
     - `red_card`: foul → card with outcome `red`; that player takes no further part, and that team's possession weight drops by 20% for the rest of the match.
     - `penalty`: foul in the box → shot from (108, 40), xg 0.78, goal.
     - If a window runs past the drawn stoppage time (for example 91–95 with only 2 minutes added), extend that period's stoppage so the beat fits.
   - After any goal, the conceding team kicks off from (60, 40).
   - Event ids are `ev-000001` upward in order; `seq` from 0; `possession_id` increments on every change of possession.
5. **`sim/__init__.py` API**: `generate(brief: MatchBrief) -> list[Event]` and `iter_events(brief) -> Iterator[Event]` (same events, lazily, in time order; Wednesday's live stream will use this).
6. **CLI**: `uv run python -m sim generate --story late_comeback --seed 7 [--home-formation 4-3-3 …] --out data/matches/<match_id>.jsonl` writes one event per line (via `model_dump_json(by_alias=True, exclude_none=True)`) plus `<match_id>.brief.json`, and prints a summary table: events, passes and pass completion per team, shots and xG per team, possession share, final score, and planted beats hit. Add `data/` to `.gitignore`.

## Tests (in `packages/sim/tests/`)

- **Determinism:** the same brief gives byte-identical JSONL; a different seed gives a different match.
- **Schema:** every event passes `Event.model_validate` and validates against `schemas/event.schema.json` with `jsonschema` (resolve `$ref` with a `referencing.Registry` the way `scripts/check_contracts.py` does). The brief validates against `match_brief.schema.json`.
- **Storylines:** for all four storylines on seeds 1–4, every planted beat produces its event inside its window, its events carry `planted_beat_id`, and the final score matches the table.
- **Plausibility (loose; calibration comes Tuesday):** events per match 1,800–3,200; passes per team 250–700; pass completion 65–92%; shots per team 3–30; total xG per match 0.5–6; `t` non-decreasing; all locations on the pitch; both periods present.
- **Dial effects:** with everything else fixed, a team with `press` 0.85 produces more pressure events and more turnovers in the opponent's half than the same team with `press` 0.25; a team with `directness` 0.85 has a longer mean pass length than with 0.2.
- **Speed:** one full match generates in under 2 seconds on a laptop.

## Conventions

- snake_case modules and functions; type hints everywhere; `mypy --strict` clean.
- Every tuned constant is a named module-level constant with a one-line comment saying what it controls.

## Verification signal (show the output)

1. `make lint typecheck test` exits 0; CI green.
2. The CLI summary table for `late_comeback` seeds 1, 2, 3 and 4.
3. The first 15 and last 15 lines of one generated JSONL.

## Omissions list (required in the PR)

Unverified behaviour, assumptions, and every place a number was chosen by feel rather than measured.

## Out of scope

Player positions and freeze frames, calibration against real data, extractors and facts, the beat detector, SSE or any API change, agents, the Composer, UI, any Azure change.
