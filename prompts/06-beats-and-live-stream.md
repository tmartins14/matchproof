# Build prompt 06 — Beat detector and the live stream

**Mode:** code. **Budget:** about 3 hours. **Branch:** `feat/beats-stream`. **Depends on:** prompt 05 merged.

## Context

Read:
- `CLAUDE.md`, `docs/VOICE.md`
- `docs/ARCHITECTURE.md` (Live mode), `docs/adr/0003-live-sse-with-cached-fallback.md`
- `schemas/beat.schema.json`, `schemas/fact.schema.json`
- `packages/sim/src/sim/positions.py` (`iter_stream`, `run`)
- `packages/intel/src/intel/engine.py` (`FactEngine`, `extract_all`), `packages/intel/src/intel/since.py`
- `services/api/src/api/main.py`

This task turns a match into a live feed: the generator's stream goes through the incremental fact engine and a new beat detector, then out to the browser over Server-Sent Events (SSE). There are no agents yet. On Thursday, the Narrator and Checker subscribe to the beats this emits. The MCP server is prompt 07.

**Two decisions are already made:**
- **Facts on the wire.** The fact registry holds about 10,800 facts per match, mostly freeze-frame facts. The stream sends only **window facts when each window closes** and **the facts attached to each beat**. Everything else stays in the registry, for MCP and the evidence rail to look up on demand.
- **The hero beat is a follow-up beat.** A red card or a goal is a beat when it happens. Its consequences ("back line dropped 7 m since the red card") can only be measured later, so the detector schedules a check after each red card and goal, and emits a second beat if the change is large enough.

Before writing: restate the task back in ten lines or fewer. Include:
- how live and batch detection stay identical,
- how follow-up beats are scheduled,
- how the frame rate on the wire is decoupled from match speed.

Then wait for my go.

## Seam rules

- Pure, deterministic Python for detection: same match, same beats, same ids. No LLM calls.
- The browser renders what the stream sends; it never computes. Every number in a beat comes from a fact in that beat's `fact_ids`.
- Schema first. The stream envelope gets a JSON Schema, and models and TypeScript types are generated from it.

## Schema change (first commit)

Add `schemas/stream_message.schema.json`:
- `seq`: integer, from 0 and increasing;
- `type`: one of `status`, `event`, `frame`, `fact`, `beat`, `claim`, `verdict`;
- `t`: match clock;
- `data`: a `$ref` to the matching schema for each type. `claim` and `verdict` are reserved for Thursday and use the existing claim schema.
- A `status` message's `data` has `state`, one of `pre_match`, `live`, `half_time`, `full_time` or `error`, plus optional `speed` and `message`.

Run `make gen` in the same commit.

## Parts

1. **`intel/beats.py`: the detector.** `BeatDetector.push(item, registry) -> list[Beat]` takes the same time-ordered items as `FactEngine`. `detect_all(events, frames, freeze_frames, registry) -> list[Beat]` must equal the live result at full time.

   **Kinds and rules.** Every threshold is a named constant with a one-line comment.

   | Kind | When it fires |
   | --- | --- |
   | `counter_goal` | A goal where possession was won in the scoring team's own half at most 15 s before the shot. |
   | `set_piece_goal` | A goal in a possession that started from a corner or free kick. |
   | `open_play_goal` | Any other goal. |
   | `high_turnover_chance` | Ball won at most 40 m from the opponent's goal, then a shot within 12 s. |
   | `big_chance` | A shot with xG at least 0.30 that doesn't score. |
   | `card` | Red cards always; yellows never in v1. |
   | `territorial_spell` | Fires when a side's territory share over a rolling 10 minutes reaches 65% or more, and closes when it falls below 55%. One beat per spell, at its close or after 15 minutes, whichever comes first. |
   | `momentum_swing` (follow-up) | 15 match minutes after every red card and every goal, call `since(anchor)`. Emit a beat anchored to that event if any of these change: back line by at least 4 m, compactness by at least 10%, possession share by at least 10 points, or territory by at least 10 points. Its facts are the before, since and change facts. |

   - **Planted beats:** if a beat's anchor event carries `planted_beat_id`, set `origin: planted` and copy the id. Otherwise `origin: detected`.
   - **`fact_ids`:** the facts that describe the beat (sequence, shot, card, freeze-frame and since facts). Never empty.
   - **Salience:** a named formula per kind, 0 to 1. Goals score highest, then red cards, then follow-ups scaled by size of change, then big chances scaled by xG, then spells. The Producer ranks on Friday; this is only the input.
   - **Labels:** `41′` for a moment, `55–70′` for a span, `90+3′` in stoppage time.
   - **Ids:** `bt-` plus the anchor event id and kind, so they are deterministic.
   - **Debounce:** no two beats of the same kind for the same side within 60 s; goals are never debounced.
2. **`services/api/src/api/live.py`: the orchestrator.** `run_live(brief, speed)` is an async generator of stream messages. It walks `sim.iter_stream`, feeds `FactEngine` and `BeatDetector`, and paces output against a real clock at `speed` match minutes per real second (1, 3 or 6, as named constants).
   - **Frames on the wire:** at most `WIRE_FPS = 10` frames per real second, whatever the speed. Send the latest frame at each tick and drop the others; the browser interpolates. Freeze frames are never streamed; they stay available by id.
   - **Facts on the wire:** window facts when each window closes, and each beat's facts immediately before that beat.
   - **Status messages:** pre-match, live, half time, full time. A comment heartbeat every 15 s of real time keeps proxies from closing the connection.
3. **API endpoints (`main.py`):**
   - `POST /matches` takes either a `MatchBrief` or `{story, seed}` (default tactics), validates it, and returns `{match_id}`. Briefs are held in memory for now; Blob storage comes later.
   - `GET /matches/{match_id}/stream?speed=3` is the SSE endpoint. Each message carries `id: <seq>`. **Resuming:** a reconnect with `Last-Event-ID` regenerates the match (it is deterministic) and resumes after that `seq` without re-sending earlier messages.
   - `GET /matches/{match_id}/facts/{fact_id}` returns one fact, for the evidence rail; 404 if unknown.
   - **Limits:** at most `MAX_STREAMS_PER_CLIENT = 2` concurrent streams per client IP, returning 429 beyond that. No model calls happen yet, but the guard belongs here.
4. **Batch path:** `uv run python -m intel beats --match data/matches/<match_id>` writes `<match_id>.beats.jsonl` and prints one line per beat: label, kind, origin, salience and fact count.

## Tests

- **Schemas:** every stream message validates against `stream_message.schema.json` and its referenced schema, on one full match at the fastest speed with pacing disabled (inject a no-op clock).
- **Ordering:** `seq` strictly increases, `t` never decreases, and every beat's facts arrive before the beat.
- **Live equals batch:** the beats in the stream equal `detect_all` for the same match, on two storylines.
- **Planted beats:** on all four storylines, seeds 1–4, every planted beat is detected with `origin: planted` and the right kind.
- **The hero follow-up:** on `red_card_flip` seeds 1–4, a follow-up `momentum_swing` beat anchored to the red card exists. Its facts include a `back_line_change` of at least 4 m for the 10-man team.
- **Wire rate:** at speed 6 with a fake clock, no real second carries more than 10 frame messages.
- **Resume:** a stream cut at `seq` N and resumed with `Last-Event-ID: N` continues at N+1 with identical content.
- **Endpoints:** `POST /matches` returns 422 for an invalid brief, the fact lookup returns 404 for an unknown id, and a third concurrent stream from one client gets 429.
- **Beats per match:** report the count for each storyline (target 12–30 before the Producer ranks); do not assert it.

## Conventions

- snake_case modules and functions; type hints everywhere; `mypy --strict` clean.
- Every threshold is a named module-level constant with a one-line comment.
- Any text shown to a viewer (labels, status messages) follows `docs/VOICE.md`.

## Verification signal (show the output)

1. `make lint typecheck test` exits 0; CI green.
2. The `intel beats` output for `red_card_flip` seed 3 and `end_to_end` seed 1.
3. The first 40 lines of `curl -N "http://localhost:8000/matches/<id>/stream?speed=6"` against `make api-dev`, plus the line that shows the red-card follow-up beat.
4. Real elapsed time for one full match at speed 6, and the number of frame messages sent.

## Omissions list (required in the PR)

Thresholds chosen by feel; any planted beat detected under a different kind than its storyline expects; and anything about pacing that wasn't measured.

## Out of scope

The MCP server (prompt 07), agents, claims and verdicts (Thursday), Producer ranking (Friday), Blob storage, UI, and any Azure or Bicep change.
