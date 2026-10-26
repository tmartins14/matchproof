# Build prompt 16 — Narrator Trials: Fixtures, the Desk model selector and cached replay

**Mode:** code, then deploy. **Budget:** about 4 hours. **Branch:** `feat/trials-desk`, stacked on `feat/trials-table` (prompt 15) until that merges. **Depends on:** prompt 15 (web export, top bar, routes, `/desk`). **Lands before:** feature freeze, Mon 8 PM ET.

## Context

This is the last step of **Rank → Inspect → Deploy**. The Desk gets a NARRATOR selector:

- The candidate the API narrates with (`live_narrator` in the web export) runs **live**, as today.
- Every other cleared candidate **replays its cached claims from the pack run**, on that fixture, labelled `CACHED · pack-v1`.

Only one model ever runs live on demo day: a second live model would add cost, 429 risk and structured-output failures on camera. Cached replay is **protected** in the cut order, because the selector depends on it.

Read:

- `CLAUDE.md`, `docs/DESIGN.md`, `docs/VOICE.md`
- prompt 15 and what it built: `src/trials/data.ts`, `TopBar.tsx`, `schemas/trials_web.schema.json`
- `docs/prototype/narrator-trials.html`: board 2 (Fixtures) and board 4 (Desk header changes). Layout and copy tone only, sample data.
- Desk: `components/desk/Desk.tsx`, `LiveDesk.tsx`, `HeaderBar.tsx`, `MatchSetupBar.tsx`, `PipelineStrip.tsx`, `ClaimItem.tsx`, `VerdictStamp.tsx`
- Live path: `live/useLiveMatch.ts`, `accumulate.ts`, `stream.ts`, `api.ts`
- `scripts/record_stream.py` and `services/api/src/api/live.py` (`run_live`, the `Pacer` protocol, `NoPacer`)
- `schemas/stream_message.schema.json`, `claim.schema.json`

## Do not touch

The API, the live stream, the agents, `evals/trials.py` scoring, the generator. Cached replay is built entirely from static files: it must work with the API down.

## Part A — Recorded fixture streams (Python), ~45 min

Generalise `scripts/record_stream.py`, or add `scripts/record_fixtures.py` beside it (keep the old one's behaviour and output for the tests):

1. For each pack fixture, build its brief from the pack (the same `Fixture.make_brief()` the trials runner uses) and play it through the real `run_live` with **no agents**, the whole match, at speed 6.
2. Use a `VirtualPacer` (in the script, not in `live.py`). `now()` returns a virtual clock and `sleep_until(t)` sets that clock to `max(now, t)`, without waiting. Each message is stamped with the virtual wall offset in ms. That keeps the condensed-playback timing (focus windows, freeze holds) the live path produces, and the recording takes seconds.
3. Write `apps/web/public/trials/streams/<fixture>.ndjson.gz`, one `{"wall_ms": n, "msg": <StreamMessage>}` per line. Gzip with mtime 0, so a second recording gives identical bytes.
4. Thin frames with the existing `thin()`. Cap each file at 1 MB, raising the frame gap the way the existing fallback does, and print sizes.

Tests:
- recording is deterministic (two runs, same bytes);
- `wall_ms` never decreases;
- the beat ids in each recording equal the beat ids in the web export's `moments` for that fixture. If they differ, the cached claims would attach to nothing. **Stop and report** rather than patching around it.

## Part B — Cached replay in the browser, ~1 h

`src/live/useCachedMatch.ts`. Same `LiveMatch` shape as `useLiveMatch` so `Desk` doesn't care which one it has, feeding the same `accumulate`:

1. Fetch `/trials/streams/<fixture>.ndjson.gz` and decompress with `DecompressionStream("gzip")`. Schedule each `msg` at `wall_ms` from kickoff with one timer loop (`requestAnimationFrame` plus elapsed time, not a timer per message). Batch the messages into the existing once-per-frame flush.
2. **Inject the candidate's claims.** When a `beat` message is dispatched, take every claim row for this candidate, fixture and beat from the results (scored or not, in index order). For each one:
   - emit a `claim` message with verdict `checking` straight away;
   - emit a `verdict` message after the row's `latency_ms` (the real on-air time from the batch run; if null, use 1500 ms).
   Claim objects must validate as `claim.schema.json`:
   - verdict mapping STANDS → `verified`, AMENDED → `rephrased`, OVERTURNED → `blocked`, HELD → `delayed`;
   - `text` and `draft_text` from the row; `reason` from the first reason;
   - `numbers` taken from the web export. Add `numbers` per claim row in `evals/trials_web.py` by running the existing `reconcile()` on the row's text and fact ids against the beat bundle (deterministic, no models). Extend that export and its schema here; that's the one Python change in this part.
   - A lost row becomes a `blocked` claim whose text is the draft (or "No claim aired") and whose reason is the lost reason.
   - Use `seq` values above the recording's last seq, so nothing collides.
3. **Speed:** cached replay runs at the recorded 6×. In cached mode, disable the speed control and show "Cached replays run at 6×".
4. **Stop/reset/unmount** clears every timer.

Tests (vitest), using a small recorded fixture plus a two-claim results slice:
- claims arrive after their beat;
- each verdict follows its claim by `latency_ms`;
- the accumulated desk matches what the live path builds for the same messages;
- a lost row renders as blocked with its reason.

## Part C — The Desk at `/desk`, ~1.25 h

**Top bar:** prompt 15's `TopBar` (lockup, nav, stepper with step 3 lit) is wired into `HeaderBar`, alongside the scorebug, clock and the existing mode/lang controls.

**Header label:** `DESK · running <model> (<rank>)`. Rank is ordinal (`1st`), from `ranks`.

**Candidate strip.** Replace today's setup source controls with a strip that has:

- **NARRATOR select.** It lists **only candidates with `cleared == true`**, in Table order, as `<id> · <rank>`. **Never list uncleared models, not even greyed out.**
  - Default: `?narrator=` if it names a cleared candidate; otherwise the Table leader.
  - Helper line under it: "Only narrators cleared for air in pack-v1."
  - The option that equals `live_narrator` is labelled `LIVE`; the others `CACHED · pack-v1`.
  - **Edge case:** if `live_narrator` is uncleared or null, every option is cached, and the strip says "Live narrator not cleared; replays only". Don't put an uncleared model back in the list.
- **REFEREE label**, fixed whatever the selection: `code checker + gpt-5-mini judge + grok-4.7 auditor · fixed`. Build it from `results.referee`, not hard-coded names.
- **FIXTURE select:** `Fixture 01 · RIV v ASH · <brief>` plus the trap chip `TRAP <clock>`. Default: `?fixture=`, else fx-01.
- **Kick off** button: "Run narrator" in live mode, "Replay cached" in cached mode.
  - Live: `POST /matches` with the fixture's `match_brief`, then stream as today (`useLiveMatch.kickoff`).
  - Cached: `useCachedMatch`.
- **Randomize and Compose** stay, for the live narrator only. In cached mode, disable them with the tooltip "Cached runs play pack fixtures only". Once a random or composed match is playing, the RECORD tile and the Compare links are hidden: there's no pack data to compare against.

**On-screen mode:** a `CACHED · pack-v1` chip next to the clock while a cached replay runs, so nobody mistakes it for live.

**Live fallback.** If a live kickoff fails with `busy`, `unreachable` or `rate_limit`, show "Live unavailable. Replay this fixture from pack-v1?" with a button. It starts the cached replay of the live narrator's own run on the same fixture. The `CACHED` chip shows, so it's honest. This is what keeps the demo safe from the container.

**RECORD tile:** replaces the least important tile in `PipelineStrip`; say which one went.
- Title: `RECORD · <MODEL> · THIS FIXTURE`.
- Counts of STANDS / AMENDED / OVERTURNED / CHECKING over the **first claim of each beat** that has landed so far (claim id ending `-01`), so it agrees with the Table's scoring.
- Below: `+<pts> pts so far`, with points from the Table's scale.
- Those counts and points add up landed claims and nothing else. If you think that crosses seam rule 3, move it into a pure helper with tests, and say so in the PR.

**NARRATOR badge** on every claim item: `NARRATOR · <MODEL>`.

**Stamp → Compare.** On every OVERTURNED or AMENDED claim, when the match is a pack fixture: "See how the others called it →" links to `/compare/<fixture>/<beat_id>?focus=<model>`. Beat ids match the pack because the generator is deterministic. Part A's test proves it for cached runs; for live runs, check one by hand and note it.

**Visual weight:** lower the stats and momentum strip a step (smaller numbers, no bars), so the claim rail reads first (prototype board 4). Pitch, rail, receipts and stats otherwise stay as built.

**URLs:** `?narrator=`, `?fixture=` and the existing review params keep the Desk shareable. Changing a select updates the URL with `router.replace`, without adding history entries.

## Part D — Fixtures at `/fixtures`, ~45 min

From prototype board 2, our pack only.

**Header:**
- title "The exam paper. Six seeded matches. Each one plants a trap.";
- the pack card: `pack-v1 · seeds 101–106`, scored moments per model, last run date;
- the referee note, plus "How a fixture is written" and "What a stamp means" (prototype copy, edited to our pack: no own goals, subs or disallowed goals).

**Grid:** one row per fixture.
- Left: the number, `RIV v ASH · <title>`, the brief, and the `TRAP <clock>` chip(s).
- Then one column per candidate in Table order. Each cell is that candidate's scored stamp on the fixture's **first trap beat**: `VerdictStamp`, or `NO CLAIM` for a lost row.
- `?fixture=` highlights that row (lime left border, scrolled into view); `?focus=` outlines that candidate's column.
- **Cell click** → `/compare/<fixture>/<trap beat>?focus=<candidate>`.

Not in this prompt: "Write a fixture" and "Promote to fixture" (cut).

## Part E — Ship, ~30 min

1. Rebuild the web export from the full `pack-v1.json` if it has landed, and record the streams.
2. `make lint typecheck check-contracts`, `uv run pytest -n 2 --dist loadfile -m "not slow"`, `cd apps/web && npm test`, `npm run build`.
3. Deploy the web as in `docs/DEPLOY.md` (`azd deploy web`).
4. On the deployed URL, walk the demo path and screenshot each step into `docs/screenshots/16/`:
   1. Table;
   2. click the **bottom cleared** row → Compare at its worst moment;
   3. `Use on Desk` → Desk with that model, `CACHED · pack-v1`;
   4. replay to the trap, stamps land, click "See how the others called it" → Compare.
   Then switch to the live narrator and run it live for 2 minutes. Both themes on the Table and the Desk.
5. Direct loads on the deployed URL:
   - `/compare/fx-03/<beat>?focus=<id>`;
   - `/desk?narrator=<cached id>&fixture=fx-05`;
   - `/fixtures?fixture=fx-02`.
   A 404 on a direct load is a blocker. Fix the SWA routing (`staticwebapp.config.json` or `trailingSlash`) before anything else.
6. Update README `## Status` and PROGRESS.md.

## Cut order inside this prompt (first to go)

1. Fixtures page polish (keep the grid and cell links)
2. Lowered visual weight of stats and momentum
3. Randomize/Compose disabled-state tooltips
4. Live fallback prompt (keep a plain "Replay cached" button)

**Protected:** NARRATOR select (cleared only), cached replay with the `CACHED · pack-v1` label, RECORD tile, the stamp → Compare link, the top bar stepper.

## Verification in the PR

The commands and outputs above, the screenshots, recording sizes, and the deployed URL. **Omissions:** what was cut, which tile RECORD replaced, any beat-id mismatch, anything checked only locally.
