# Build prompt 15 — Narrator Trials: web data export, top bar, the Table and Compare

**Mode:** code. **Budget:** about 3.5 hours. **Branch:** `feat/trials-table`, stacked on `feat/narrator-trials` until PR 35 merges, then rebased on `main`. **Depends on:** PR 35 with prompt 14.1 (its schema: `lost`, `narrator_ms`, `referee_split`, `on_air_p90_ms`). **Lands before:** prompt 16 (Fixtures, Desk selector, cached replay).

Build against `evals/reports/trials/pack-v1-smoke.json` until the full run lands. The full `pack-v1.json` has the same shape; switching is a rebuild, not a code change.

## Context

Matchproof is now **Narrator Trials**: "You want an AI narrator? It has to pass this test first." The flow is a drill-down, **Rank → Inspect → Deploy**: Table (rank) → Compare and Fixtures (inspect) → Desk (deploy). Nav stays free, and no page is gated behind another.

Read:

- `CLAUDE.md`. Seam rule 3 matters most here: the browser draws JSON and never computes. Rankings, worst moments, picks and clock labels are computed in Python.
- `docs/DESIGN.md`, `docs/VOICE.md`, `apps/web/src/theme/tokens.ts`
- `docs/prototype/narrator-trials.html`. Tyler commits this; if it's missing, ask him for `Matchproof_Narrator_Trials.html`. Board 1 is the Table, board 3 is Compare, board 4 is the Desk header. **It holds sample data:** take the layout, hierarchy and copy tone from it, never its numbers, models or fixtures. In particular, mistral-small, llama, "disallowed goal" and "own goal" are not in our pack.
- `schemas/trials_results.schema.json` and `evals/trials.py` (what the results mean)
- `apps/web/src/components/desk/HeaderBar.tsx`, `Wordmark.tsx`, `VerdictStamp.tsx`, `apps/web/src/viz/Pitch.tsx`, `apps/web/src/desk/copy.ts`, `apps/web/src/copy/en.json`, `apps/web/src/app/page.tsx`, `Home.tsx`
- `apps/web/next.config.ts` (`output: "export"`: static pages, so every query param is read on the client)

## Do not touch

The generator, extractors, Checker, judge, auditor, consensus, the live stream, the API and `evals/trials.py` scoring. Don't re-run the pack for this task.

## Part A — Web export (Python, no model calls), ~45 min

`evals/trials_web.py`: reads a results file, rebuilds each fixture's match from the pack (cached generation, deterministic, no models) and writes `apps/web/fixtures/trials/web-<pack>.json`. Schema: `schemas/trials_web.schema.json` plus an example; run `make gen` and `make check-contracts`.

```
uv run python -m evals.trials_web evals/reports/trials/pack-v1-smoke.json   # writes web-pack-v1-smoke.json
uv run python -m evals.trials_web evals/reports/trials/pack-v1.json         # writes web-pack-v1.json
```

It holds everything the pages draw, so the browser never derives anything:

- **`results`:** the results file as is.
- **`ranks`:** `{candidate: 1-based rank}` in summary order.
- **`worst`:** per candidate, `{fixture, beat, verdict, note}`. Take the candidate's lowest scored verdict (OVERTURNED < AMENDED < HELD < STANDS); on a tie, the latest beat. `note` is one short line: the `failed_span` → `corrected_span` for AMENDED, otherwise the first reason trimmed to 110 characters.
- **`picks`**, each null when nothing qualifies:
  - `live_feed`: cleared, lowest `p90_ms`;
  - `budget`: cleared, lowest numeric `usd_per_match`;
  - `not_cleared`: every uncleared candidate id.
- **`live_narrator`:** the candidate id whose `deployment` equals `models.yaml` `narrator.deployment` (the model the API narrates with live), else null.
- **`fixtures[]`:** each pack fixture plus:
  - `match_brief`: the full MatchBrief JSON, so prompt 16 can `POST /matches` a custom fixture;
  - `trap_beats`: the beat anchored on each trap's `event_id`.
- **`moments`:** keyed by fixture then beat, for every beat any candidate was scored on:
  - `kind`, `label`, `clock` (broadcast clock, e.g. `90+4′`, from the existing display formatter, not a new one), `t`;
  - `facts`: the beat bundle's facts as `{id, label, text}`, with `text` the English display rendering already used by the Desk;
  - `sources`: up to 6 source events as `{id, type, player, clock}`;
  - `freeze`: the anchor event's freeze frame, in the shape `Pitch.tsx` already draws.
- **`claim_clock`:** `{claim row index: clock}`, or put `clock` on each claim row in the export. Either is fine; say which.

Size check: print the file size. If it's over 1.5 MB, drop `freeze` for beats that are neither trap beats nor any candidate's worst moment, and say so.

Tests:
- the worst-moment rule (tie goes to the latest);
- picks with an unpriced candidate (it is never the budget pick);
- `live_narrator` lookup;
- the trap beat resolves for every pack fixture;
- the export validates against its schema.

## Part B — Routes and the shared top bar, ~45 min

**Routes** (static export; check each one loads on a direct visit, not only through client navigation):

| route | page |
| --- | --- |
| `/` | the Table (new home) |
| `/compare/[fixture]/[beat]` | Compare. Use `generateStaticParams` from the export's `moments` keys. Beat ids, not event ids: one beat per anchor event, and claims carry beat ids. |
| `/compare` | client redirect to fx-01's first trap beat |
| `/fixtures` | placeholder that prompt 16 fills ("Fixtures: coming in prompt 16" is fine for now) |
| `/desk` | the Desk, **moved from `/`**. Keep `?source=fixture` and the review params working at `/desk`. Update `e2e/shots.spec.ts`, `scripts/smoke_prod.sh` and any link or doc that assumes the Desk is at `/`. |

The JSON is imported at build time from `apps/web/fixtures/trials/web-pack-v1.json`. Fall back to `web-pack-v1-smoke.json` when the full file isn't there yet, through one module, `src/trials/data.ts`. Its typed accessors (`candidateById`, `momentOf`, `rankOf`, …) do lookups only, no maths.

**Top bar** (`src/components/trials/TopBar.tsx`), used on every page including the Desk (prompt 16 wires it into `HeaderBar`). Left to right:

- **Lockup:** `MATCHPROOF` + `NARRATOR TRIALS` (extend `Wordmark`; follow the prototype).
- **Nav:** `TABLE · FIXTURES · COMPARE · DESK`, active one filled lime.
- **Stepper:** `1 Rank · 2 Inspect · 3 Deploy`. Lit step: Table = 1, Compare and Fixtures = 2, Desk = 3. The lit step gets a plain lime underline; the others are plain text. Steps are not links and nothing animates. Mark it up as a list with `aria-current="step"` on the lit one.
- **Right:** `pack-v1 · run <date>`, plus a `SMOKE DATA` chip when the smoke file is in use.

EN/ES and Fan/Analyst/Producer stay on the Desk only; they're not on the other pages.

Copy goes in `copy/en.json` under `trials.*` and passes `voice/banned.yaml`. If a test requires EN/ES key parity, add the ES keys too.

## Part C — The Table at `/`, ~1 h

From prototype board 1, with these changes.

**Hero card:** "Who do you put on air?" Headline from the data: `<N> narrator models. <M> rigged fixtures. One fixed referee.` One line on how it works, following the prototype.

**Referee card:** `Checker · code`, `Judge · <judge>`, `Auditor · <auditor>`, then "Fixed for every narrator." Where any candidate is `self_audited`, add a line: "grok-4.7 is audited by its own model; read its row with that in mind."

**Scoring card:** STANDS +3, AMENDED +1, OVERTURNED −3, plus "HELD (no answer from the model): not scored".

**League table**, one row per summary row, in order. Columns:
- `#`; Narrator (name, then `Microsoft Foundry · worst: <worst.note> (Fixture NN, <clock>)` underneath);
- Claims, Stands, Amended, Overturned, Pts;
- Clean % (`clean_pct`); p90 (`p90_ms`, as `1.9 s`); $/match (`usd_per_match`, or "price not set"), with tokens per match small underneath;
- Fail profile: a single stacked bar of `fail_profile` with a text legend on hover/focus (one token colour per bucket, never colour alone; follow `dataviz` rules if loaded);
- Form: last-five chips (S/A/O/H), using the verdict tokens.

**Row states:**
- uncleared rows get a red left border and a `NOT CLEARED FOR AIR` tag;
- the leader gets the lime left border.
- If the referees split on a row (`referee_splits > 0`), show `referees split on N` in small text under Overturned, so a judge can see the referee isn't infallible.

**Row click** (the whole row, keyboard too): go to `/compare/<worst.fixture>/<worst.beat>?focus=<candidate>`.

**`Use on Desk`** button, on cleared rows only: go to `/desk?narrator=<candidate>&fixture=<worst.fixture>`. It must not also trigger the row click.

**Pick cards** under the table, from `picks`:
- **Live feed pick:** `<id> · p90 <x> s`;
- **Budget pick:** `<id> · $<x> per match`;
- **Not cleared for air:** the ids.

Leave a card out when its pick is null.

**Footer cards:**
- **Relegation rule:** "More OVERTURNED than AMENDED: not cleared for air."
- **Re-run on update:** same six seeds, same referee, and a vendor update re-runs the table.

**Next up** strip (small, last; cut it first if time runs short): read from `evals/trials/next_up.yaml` (new; Tyler edits it) and pass it through the export. Each entry is `{model, reason}`, with true reasons only. Seed it with:
- Claude Sonnet 5.5 — awaiting Marketplace access;
- mistral-small — rejects a required call parameter (PR 35);
- "Your model — one line of config, then run the pack".

## Part D — Compare at `/compare/[fixture]/[beat]`, ~1 h

From prototype board 3.

**Top-right crumb:** `Fixture NN · RIV v ASH · moment`, then a chip with `<clock> <label>`.

**Left column**, from `moments`:
- the freeze frame, using `Pitch.tsx` (no new pitch code);
- "Computed facts (the only numbers allowed)": label and text, with the fact id small underneath;
- the source events table.

**Right**, headline "Same moment. <N> narrators. One referee." and the note "Prose is not ranked. Only what failed is highlighted."

**One card per candidate**, in Table order. Each card shows that candidate's **scored** claim on this beat:
- `NARRATOR · <rank>`, the name, and the verdict stamp (`VerdictStamp`);
- the text. For AMENDED, the draft's `failed_span` is shown struck through in red, followed by the `corrected_span` in amber, as in the prototype. For OVERTURNED, the text as is, with the reason below;
- a mono line: `checker: <checker> · auditor: <auditor> · <narrator_ms as s>`, plus `· referees split` when `referee_split` is true;
- a lost row (`lost` not null): "No claim aired: <reason>". For `rejected`, also show the draft text with "cited a fact that does not exist".
- `?focus=<candidate>`: scroll that card into view and give it the lime outline.

**`Use on Desk`** on **cleared candidates' cards only**. Uncleared cards show `NOT CLEARED FOR AIR` instead. The Desk selector only lists cleared models (prompt 16), so a button that leads to a model the Desk can't select would be a dead end. Link: `/desk?narrator=<id>&fixture=<fixture>`.

**Bottom-right note card:**
- "Code reconciles every number and name against the fact registry before any model reads the sentence. The judge and the auditor only judge wording."
- "See the fixture this came from →" → `/fixtures?fixture=<fixture>&focus=<candidate if any>`.

**Prev/next moment arrows** inside the fixture, keyboard `←/→`. Use the beat order from `moments`.

## Verification in the PR

- `make lint typecheck check-contracts`; `uv run pytest -n 2 --dist loadfile -m "not slow"` (not `-n auto`: it ran out of memory on this machine); `cd apps/web && npm test`.
- `npm run build` succeeds, and these direct loads of the static `out/` work:
  - `/`;
  - `/compare/fx-01/<a real beat>?focus=gpt-5-nano`;
  - `/desk`;
  - `/desk?source=fixture`.
- Screenshots of the Table and of one Compare page, both themes, at 1440 and 390 wide, into `docs/screenshots/15/`.
- Web export file size.
- The worst moment for each candidate in the smoke data, so Tyler can check the rule picked a sensible one.

## Omissions to state

- Built on smoke data if the full run hadn't landed. Say which file the screenshots use.
- Anything in the prototype left out.

## Cut order inside this prompt

1. Next up strip
2. Prev/next arrows
3. Fail profile hover legend (keep the bar)
4. Pick cards

The Table rows, row click, `Use on Desk` and the Compare cards are protected.
