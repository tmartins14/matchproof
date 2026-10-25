# Build prompt 12 — Live wiring: the desk plays a real match

**Mode:** code. **Budget:** about 4 hours. **Branch:** `feat/live-desk`. **Depends on:** PR 28 merged. **Lands before:** prompt 13 (deploy to Static Web Apps, cached replay, pre-generated matches).

## Context

Read:

- `CLAUDE.md` (seam rules)
- `docs/ARCHITECTURE.md` (Pipeline, Match storage)
- `docs/DESIGN.md`
- `docs/VOICE.md`
- `schemas/stream_message.schema.json`, `beat.schema.json` and `claim.schema.json`
- `services/api/src/api/live.py` (`pipeline`, `schedule`) and `main.py` (`/matches`, `/matches/random`, `/compose`, `/stream`)
- `scripts/make_desk_fixture.py`
- in `apps/web/src/desk/`: `fixture.ts`, `model.ts`, `statsModel.ts`, `railModel.ts`, `pitchModel.ts` and `reviewParams.ts`
- `apps/web/src/components/desk/Desk.tsx`

The desk renders from a static fixture. This task makes it play a real match: the setup controls call the API, the SSE stream fills the desk as the match plays, and the desk follows the live state (focus, freeze, half time, full time).

The stream already carries:

- events;
- frames at up to 10 a second;
- window and desk facts as their spans close, with `label`;
- beats with their facts;
- claims and verdicts, including corrections;
- statuses: `pre_match`, `live`, `focus`, `freeze` (the freeze frame follows as the next `frame`), `half_time`, `full_time` and `notice`.

Four things the fixture script derives are **not** on the stream yet. Part 0 adds them in Python, so the browser still computes no football statistics.

Before writing: restate the task in ten lines or fewer. Include the two schema changes, how the stream state reaches the existing builders, how you will test without a running API in CI, and how a reconnect is handled. Wait for my go.

## Seam rules

- The browser renders. It may count messages it received (pipeline counters) and look facts up by name. It may not compute a score, a share, a total or a difference.
- Schema change, then `make gen` in the same PR.
- Recorded stream fixtures are real API output, never hand-written.
- The words AI, agent, model and generated stay out of the desk UI.

## Part 0 — API prerequisites (Python, first commit)

1. **CORS.** Add `CORSMiddleware` to the API. Allowed origins come from the env var `WEB_ORIGINS` (comma-separated), defaulting to `http://localhost:3000`. Allow `GET` and `POST`, and the `Content-Type` and `Last-Event-ID` headers. Prompt 13 adds the production origins.
2. **Score on the stream.**
   - Add `score` to the status `state` enum, plus an optional `score` object `{home, away}` (non-negative integers) on the status data.
   - After every goal event, the pipeline sends a `score` status with the new score, from `intel.score.match_score`. `full_time` also carries `score`.
   - The scorebug reads only these. Remove the regex parsing of `score_after` prose from the fixture script; the fixture's `score_timeline` comes from the same function.
3. **Highlights on beats.**
   - Move `highlight_for` from `make_desk_fixture.py` into `intel/desk.py`.
   - Add an optional `highlight` to `beat.schema.json`: `{player_ids?: string[], zone?: {x_from, x_to}}`.
   - The pipeline sets it on every beat it sends. The fixture script uses the same function.
4. **Source descriptions.**
   - Add `GET /matches/{match_id}/sources/{source_id}`. It returns `{kind: "aggregate", description}`, `{kind: "window", t_from, t_to}` or `{kind: "freeze_frame", event_id}`, with 404 for an unknown id.
   - It works for a match that is streaming and for an archived one. The evidence rail fetches it on demand for non-event sources.
5. **Match ids.** `store_brief` must also check the archive. A different brief under an id that is already archived gets the hash suffix, as in memory, so an edited brief can never stream under an archived match's id.
6. Run `make gen`. Add tests for all five parts: CORS preflight from an allowed and a disallowed origin, score statuses after each goal on a short match, highlights on beats, the sources route for each kind plus a 404, and the archived-id collision.

## Parts

1. **One data shape for the desk.**
   - Rename `DeskFixture` to `DeskData`. The builders (`model`, `statsModel`, `railModel`, `pitchModel`) keep taking it.
   - The static fixture is one source of `DeskData`. A live accumulator is the other.
   - Add `phase` (`pre`, `connecting`, `live`, `focus`, `freeze`, `half_time`, `full_time`, `error`), `clock` (the latest `t`) and `liveFrame` (the latest streamed frame).
2. **Live accumulator** (`src/live/accumulate.ts`). A pure reducer: `(DeskData, StreamMessage) → DeskData`, with O(1) work per message.
   - **Events:**
     - append to the event store;
     - keep the latest 5 ids for the ticker;
     - increment the events counter.
   - **Frames:**
     - `liveFrame` = the latest frame;
     - a frame that directly follows a `freeze` status is stored in `frames[event_id]`.
   - **Facts:**
     - store by id and increment the facts counter;
     - index running-total and momentum facts by name (`to NN′`, `min-NN`) the same way the fixture script does. That is a lookup, not arithmetic.
   - **Beats:** append, with `highlight` from the beat.
   - **Claims and verdicts:**
     - the last message per claim id wins;
     - a verdict with `correction` replaces the text and keeps `draft_text`, as the schema describes.
   - **Statuses:**
     - set `phase`;
     - `score` sets the score;
     - `notice` queues a viewer notice.
   - Rendering is batched to one React update per animation frame, so 10 frames a second never re-render the page 10 times.
3. **API client and stream** (`src/live/api.ts`, `src/live/stream.ts`).
   - The base URL comes from `NEXT_PUBLIC_API_URL`, defaulting to `http://localhost:8000`.
   - `EventSource` on `/matches/{id}/stream?speed=N`.
   - **No silent reconnects.** On error, close the source, set `phase: error` and show the notice "Connection lost." with a New match button. A resumed stream with agents can't replay agent messages, so auto-reconnect would desync the desk. Prompt 13 adds the cached fallback.
   - A 503 with `{fallback: "cached"}` and a 429 both show a notice and leave the desk in pre-match.
4. **Setup controls.**
   - **Randomize:** `POST /matches/random`. The returned brief replaces the current one, and the summary and tactics update.
   - **Read brief:**
     - `POST /compose {text}`. The returned brief and `brief_text` replace the current ones.
     - Warnings show under the textarea in `muted`.
     - A 429 or a cap shows a notice.
     - While the request is in flight, the button shows "Reading…" and is disabled. No spinner.
   - **Tactics edits** (formation, three dials, storyline) write into the brief's matching fields. This is form state, not computation.
   - **Kick off live:** `POST /matches` with the brief, then open the stream with the `match_id` it returns.
     - The speed (1×, 3×, 6×) is chosen before kickoff. While live, the speed control shows the chosen speed and is disabled, because the API can't change speed mid-stream.
   - **New match:**
     - closes the stream and returns to pre-match;
     - the brief is kept;
     - the desk clears.
   - **Watch cached replay:** disabled, with the `title` "Available soon". Prompt 13 wires it.
5. **Live state on the desk.**
   - **Scorebug:**
     - The clock comes from `clock`, in the broadcast format the copy files use.
     - LIVE shows while `live` or `focus`.
     - HT shows at half time, FT at full time.
   - **Pitch:**
     - It draws `liveFrame` while live.
     - On `freeze`, it draws the anchor's freeze frame, holds it, and shows the lower-third caption "Freeze frame, mm:ss".
     - When a beat is pinned (below), it draws that beat's freeze frame.
     - A CHECKING claim highlights its beat's `highlight`.
   - **Focus:** while `focus`, the caption reads "Slowing down for a moment" (copy, en and es). Nothing else changes.
   - **Follow live:**
     - By default the desk follows: when a beat airs, it becomes the selected beat and its first claim the selected claim.
     - Clicking another beat or claim pins it, and a "Follow live" button appears in the pitch header (as in the prototype). Clicking it resumes following.
   - **Notices:** a viewer notice shows for 6 s in a `role="status"` line under the setup bar. "Narration paused" and similar come from the server's text.
   - **Before kickoff:** the desk shows the pre-match state. The pitch shows the brief's starting shape (copy "Starting shape"), with no claims or stats. The feed and rail show their empty text from copy.
6. **Fixture mode stays for review.**
   - `?source=fixture` renders the static fixture exactly as today, and the review parameters (`beat`, `claim`, `stamp`, `setup`) only apply there.
   - `npm run shots` and the vitest suite use fixture mode.
   - Live is the default.
7. **Recorded stream for tests.**
   - `scripts/record_stream.py` plays one short match (`red_card_flip` seed 3, `until_s` at about 25 minutes past the red card) through the real `run_live` with a no-op pacer and no agents. It writes `apps/web/fixtures/stream-short.ndjson`, one stream message per line, under 400 KB. Drop frames except one per match second and the freeze frames.
   - Tests:
     - The reducer over the recorded stream gives the beats, the score after each goal, and freeze frames for every beat anchor.
     - Last-wins and corrections on synthetic claim updates built from recorded claims.
     - Follow-live pinning.
     - A Playwright test that serves the recorded stream through `page.route` as `text/event-stream`, kicks off, and asserts that the scorebug reaches the recorded final score and FT shows.

8. **Align the key-moment headlines (last, as its own commit).** In the key-moment feed, the minute block (`.mp-minute`) grows with its label, so headlines start at different x positions: "42–52′" pushes its headline right of "63′" and "9′". Fix it in `desk.css` and `KeyMomentRow.tsx`:
   - **Fixed width:** give the minute block `flex: none; width: 96px; box-sizing: border-box`, with the label left-aligned at the current padding. 96 px fits "90+4′" and "42–52′" in 17px Archivo Narrow 600. Check that before settling on it.
   - **Long labels:** a label longer than 6 characters (for example "45+3–52′") gets the class `mp-minute--long` (15px), so it stays inside the same width. The block never grows.
   - **CHECKING rows:** these use the same minute block width, so their headline lines up with the solid rows.
   - **At 390:** the width drops to 80px, and the long class to 14px.
   - **Test:** in fixture mode, render rows labelled "9′", "63′", "42–52′", "90+4′" and "45+3–52′". Assert with Playwright `boundingBox` that the headline elements share the same left offset, at 1440 and 390.
   - **Screenshots:** re-shoot `desk-1440.png` and `desk-390.png`, and add a `feed-1440.png` crop of the key-moments column to `npm run shots`.

## Verification signal (show the output)

1. `make check-contracts lint typecheck test` exits 0, and `cd apps/web && npm run build` exits 0. CI is green.
2. The vitest and Playwright summaries, including the recorded-stream e2e and the headline-alignment test. Embed `feed-1440.png` in the PR.
3. **Local end to end, with agents** (needs `az login` and the Foundry settings from `azd env get-values`):
   - run `make api-dev` and `make web-dev`;
   - Randomize once, then set the storyline to `red_card_flip`;
   - Kick off at 6× and play to full time.

   Attach screenshots of:
   - pre-match;
   - live while cruising;
   - a freeze frame with its caption;
   - a claim going from CHECKING to its verdict;
   - an AMENDED or OVERTURNED claim if one occurs;
   - full time with FT.

   If agents can't run locally, say so, run it without agents, and mark this item not done. Don't fake verdicts.
4. **Archive check.** After that full-time run, wait 60 s, then print `jq '.claims | length' data/archive/<match_id>/claim_graph.json` and the verdict counts. Report the result; don't fix anything here. If the count is 0 while the stream showed claims, write down exactly what the stream showed and what the archive holds.

## Omissions list (required in the PR)

- Anything checked only in fixture mode, or only without agents.
- Behaviour on a slow connection.
- Any status or message type the desk ignores.

## Out of scope

- Deploy, Static Web Apps and production CORS origins (prompt 13).
- Cached replay and the 503 fallback path (prompt 13).
- The Localizer.
- The overlay route.
- Changing speed mid-match.
- Narrator mode per viewer: the stream's narration mode stays server-side; the desk's mode switch changes display only.
