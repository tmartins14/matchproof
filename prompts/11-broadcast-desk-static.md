# Build prompt 11 — Floodlight theme and the static live desk

**Mode:** code. **Budget:** about 3 hours. **Branch:** `feat/desk-static`. **Depends on:** prompt 10 merged. **Lands before:** prompt 12 (live wiring: SSE, state machine, deploy).

## Context

Read `CLAUDE.md`, then:

- `docs/DESIGN.md`: new in this PR (Part 0). The visual system. It wins over everything else on looks.
- `docs/adr/0006-two-themes-one-token-file.md`, with the addendum from Part 0.
- `docs/VOICE.md`: Visual rules and On-screen verdict vocabulary.
- `docs/prototype/README.md`.
- `docs/prototype/Main.dc.html`, updated in Part 0. Read the Broadcast branch of `tokens()`, the markup and `renderVals()` for every component and state. Ignore the Editorial branch and the theme toggle.
- `docs/prototype/reference/*.png`, added in Part 0. Your visual target: `Main.dc.html` does not run on its own.
- `schemas/claim_graph.schema.json`, `beat`, `claim`, `fact`, `position_frame`.
- `apps/web/src/theme/tokens.ts` and `apps/web/src/copy/*.json`.

### Reference quirks: do not copy

The references are the target for look and feel, not a pixel spec. These things in them are prototype artefacts:

- **The Broadcast/Editorial and Match/Calibration toggles.** Neither ships in this prompt. The header holds the wordmark, scorebug, mode and language only, on one row at 1440 wide.
- **The verdict stamp wrapping under the headline in a key-moment bar.** The stamp stays at the right edge of the bar; the headline wraps instead.
- **The lime sweep showing through the header toggles and the evidence rail edge.** The backdrop never sits behind text or controls. Give any group that floats over it a solid `surface` background, or keep the sweep in the empty gutter.
- **"Live" still showing at 96:00.** At full time the scorebug shows FT, not LIVE.
- **The Checker stage saying "verified, rephrased, blocked".** Use the copy-file labels: "11 stand · 1 amended · 1 overturned".
- **"Brief rewritten from the tactics." staying on screen.** It is a transient status: clear it after 4 seconds or on the next edit.
- **The receipt rail with no stat card and no HELD stamp.** `docs/DESIGN.md` adds both; build them.

`apps/web` is still a scaffold. This task builds the live desk as React components rendered from a **fixture** claim graph, in the single Broadcast theme ("Floodlight"), so the design can be reviewed and merged before any live wiring. Prompt 12 connects it to SSE.

Before writing: restate the task in eight lines or fewer, including the component list, how you will source the fixture, and how tokens reach components. Wait for my go.

## Seam rules

- **The browser renders.** No football statistics are computed in the browser. Every number on screen comes from a fact, a beat or a position frame in the fixture. If a panel row has no fact behind it in the fixture, leave the row out and list it in the omissions.
- **Components read tokens only** (ADR 0006). No hex, rgb or named colours in `src/components/` or `src/viz/`.
- **Copy from the copy files.** Every visible string comes from `src/copy/en.json` or `es.json`. The words AI, agent, model and generated never appear in the desk.
- **Fixtures are real pipeline output.** Never hand-write a claim, fact or frame.

## Part 0 — Docs (separate commit, first)

1. Add `docs/DESIGN.md` (attached).
2. Replace `docs/prototype/Main.dc.html` with the attached version.
3. Add the attached reference screenshots to `docs/prototype/reference/`:
   - `broadcast.png`, mid-match;
   - `broadcast-setup-open.png`, pre-match with setup expanded.
4. In ADR 0006, append under Decision:

   > **Oct 23 addendum.** Editorial is deferred to after submission; Broadcast ("Floodlight", `docs/DESIGN.md`) ships alone. Reason: judges score mostly from the video, a theme toggle shows nothing about verification, and two themes double the UI work in the last four days. The single token file and the colour-literal lint stay, so Editorial can return as a second token set without component changes.

   Set the status line to `accepted, 2026-10-18; amended 2026-10-23`.
5. In `docs/SPEC.md`:
   - In the Hackathon fit table, UX & Presentation becomes "Live desk with evidence rail and on-screen review states, three modes, two languages; product text follows `docs/VOICE.md`".
   - In What it does, item 6, remove "and theme (Broadcast, Editorial)".
6. In `docs/PLAN.md` Design process, add one line: "Oct 23: design pass done on Friday. One theme, Floodlight; see `docs/DESIGN.md`. Editorial deferred (ADR 0006 addendum)."
7. In `docs/prototype/README.md`:
   - Replace "Broadcast theme colours and type are placeholders" with "The prototype still has an Editorial toggle; the build ships Broadcast only."
   - Add under "Changed since the prototype": "Oct 23 design pass: Broadcast is now Floodlight (`docs/DESIGN.md`); the match setup collapses to one bar and expands on Edit; Editorial deferred."
   - Add: "`prototype.html` predates the design pass. `Main.dc.html` and `reference/` are authoritative."

## Parts

1. **Tokens.**
   - Rewrite `apps/web/src/theme/tokens.ts` as one token set named and valued as in the `docs/DESIGN.md` tables: colour, type, shape. Keep the shape `export const themes = { broadcast: {...} }` with `ThemeName = "broadcast"`, so a second theme can be added later without touching components.
   - Store values, not CSS declarations. For example, `cut: "polygon(8px 0, 100% 0, calc(100% - 8px) 100%, 0 100%)"`.
   - Delete the Editorial set. Update any import that used it.
   - A unit test: no token value is `undefined` or empty.
2. **Colour-literal lint.** If it does not exist yet, add the ADR 0006 rule: lint or test fails on colour literals in `src/components/**` and `src/viz/**`. Show it failing on a planted `#fff`, then remove the plant.
3. **Fonts and token plumbing.**
   - Fonts through `next/font/google` only: Archivo Narrow (600, 700), Archivo (400, 500, 600, 800), Geist Mono (400, 500).
   - Expose tokens as CSS custom properties on the root (`--mp-<token>`), written once from `tokens.ts` in the root layout. Components use `var(--mp-…)`.
   - Mode (fan, analyst, producer) and language are client state. There is no theme toggle.
4. **Fixture.**
   - `scripts/make_desk_fixture.py` builds `apps/web/fixtures/desk.json` from an archived match (`data/archive/<id>/`): the claim graph, the freeze frame for each beat's anchor event, the final score and the brief. Keep it under 400 KB.
   - The fixture must contain at least one claim per verdict: `verified`, `rephrased` (with `draft_text`), `blocked` and `delayed`. If one match lacks a verdict, merge beats from a second archived match and say which.
   - Add a typed loader that validates the fixture against the generated types at build time.
   - Build a static **desk snapshot** for review:
     - clock at 71′;
     - beats up to 71′ revealed;
     - the latest beat's claims `checking`.

     Select other states with query parameters (Part 6).
5. **Components.** In `src/components/desk/` and `src/viz/`, each matching the prototype markup, the references and the DESIGN.md entry of the same name:
   - `Backdrop`
   - `Wordmark`
   - `Scorebug`
   - `SegmentedControl`
   - `HeaderBar`
   - `MatchSetupBar`
     - A collapsed summary row; Edit expands it, with `aria-expanded`, and the chevron rotates.
     - The tactics inputs show the brief's values.
     - Kick off, Randomize and Watch cached replay render but do nothing yet.
   - `PipelineStrip`
   - `SectionTab`
   - `Pitch`: SVG markings, players and ball from the freeze frame, the `zone` highlight while checking, and the lower-third caption.
   - `StatsPanel`
   - `MomentumStrip`, with moment pins
   - `KeyMomentFeed` and `KeyMomentRow`: lower-third bars with expandable claims.
   - `VerdictStamp`: CHECKING, STANDS, AMENDED, OVERTURNED and HELD, per the DESIGN.md table.
   - `ClaimItem`: AMENDED shows `draft_text` struck through above the new text; OVERTURNED strikes the text and shows the reason.
   - `EvidenceRail`, with `StatCard` at the top.

   Modes change content, not layout:
   - **Fan:** prose per beat.
   - **Analyst:** claims, fact IDs and the evidence rail.
   - **Producer:** Analyst plus counts of removed claims.
6. **Page and review states.**
   - `/` renders the desk from the fixture.
   - Query parameters for review and screenshots: `lang`, `mode`, `beat` (selected beat id), `claim` (selected claim id), `setup=open`.
   - These are review aids. Keep them in one small module that prompt 12 can drop.
7. **Screenshots.** A Playwright script, `npm run shots`, writes to `docs/screenshots/11/`:
   - `desk-1440.png` and `desk-390.png` (analyst, 1440 × 900 and 390 × 844);
   - `setup-open-1440.png`;
   - `fan-1440.png`;
   - `es-1440.png`;
   - one crop per verdict stamp: CHECKING, STANDS, AMENDED, OVERTURNED, HELD.
8. **Accessibility.**
   - An inset focus ring on every element with a cut (DESIGN.md, Shape and depth).
   - Touch targets of at least 44 px.
   - Run `@axe-core/playwright` on the desk at both widths. Zero serious or critical violations.

## Acceptance

At 1440 wide, the desk matches `docs/prototype/reference/`. Put each of your screenshots beside its reference in the PR. Check specifically:

- the chevron backdrop and lime sweep;
- the lockup wordmark;
- white slanted section tabs;
- hard offset shadows with no blur on the scorebug, panels and moment bars;
- key moments as white lower-third bars with a dark minute block;
- filled slanted stamps;
- the lime lower-third caption on the pitch;
- slanted pipeline blocks;
- the collapsed setup bar.

Also:

- At 390 wide, nothing overflows horizontally. The backdrop may crop.
- `grep` finds no colour literals in components.
- No banned words or visuals from `docs/VOICE.md`.

## Conventions

- camelCase function and method names. No default exports except Next.js pages and layouts.
- Each component stays under 200 lines; split before that.
- No new runtime dependencies except D3 modules you actually use. Say which, and why.

## Verification signal (show the output)

1. `make lint typecheck test` exits 0, and `cd apps/web && npm run build` exits 0. CI is green.
2. The colour-literal lint failing on the planted literal, then passing.
3. `npm run shots`: the file list, with the screenshots embedded in the PR beside the references.
4. The axe summary at both widths.
5. `make_desk_fixture.py` output: the match ids used, the verdict counts and the fixture size.

## Omissions list (required in the PR)

- Every place the build differs from the references or DESIGN.md, and why.
- Any panel row left out for lack of a fact.
- Tokens renamed from the prototype.
- Anything checked at only one width.

## Out of scope

- SSE and the live state machine: pre-match → live → full time, speeds, freeze-frame timing, Follow live.
- Loading matches from the API.
- Static Web Apps deploy.
- The overlay route, the Localizer, the Calibration view and the Producer agent log.
- Any second theme.
- Any Python change beyond the fixture script.
