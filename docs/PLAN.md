# Matchproof — 10-Day Build Plan

Oct 17, 2026 · @Tyler · updated Oct 19 (positioning, judge model, voice)

## TL;DR

We ship **Matchproof** ("Set the tactics. Watch the match. Every claim proven.") by Tue Oct 27, 9 PM ET: an agent system that composes a synthetic, football-realistic match from a tactical brief, explains it beat by beat, and proves every sentence against the event log. The official deadline is Oct 27, 11:59 PM PT (Oct 28, 2:59 AM ET), so the internal target leaves a 6-hour buffer.

The three bets that win points:

1. **A match you control, as a scenario harness.** Tactics in, a different match out, the same one every time for the same seed. For fans it's a sandbox; for an enterprise buyer it's how you certify a narration system: controlled inputs, known ground truth, a measured catch rate. Few entries simulate or track positions; this is the opening shot of the video.
2. **Verification you can watch.** Every claim links to a computed fact and its event IDs. On screen it shows CHECKING while the pitch highlights the evidence, then STANDS, AMENDED or OVERTURNED. The judge is a different model from a different vendor (Claude Sonnet 5.5 judges gpt-5-mini). About 50 entries promise verification; few show it happening, and fewer check positional claims against freeze frames.
3. **Microsoft hero stack used where it earns its place.** Microsoft Foundry for models and agents, Microsoft Agent Framework for orchestration, an MCP server for match data, Azure AI Translator, Container Apps, Static Web Apps, Blob Storage and Application Insights, all deployed with azd and Bicep.

See **Positioning** below for why the order of these bets changed on Oct 19.

Capacity is about 57 focused hours, with Oct 26 and 27 taken off. Feature freeze is 8 PM Mon Oct 26. Anything not done by then moves to the cut list.

## Positioning (Oct 19)

A review of the 303 entries on the Innovation Studio projects page (titles and short descriptions only, so counts are rough) changed the pitch, not the build:

| Theme | Entries |
| --- | --- |
| Verified or evidence-backed narration | ~51 |
| Broadcast or overlays | ~53 |
| Multi-agent "studio crew" | ~48 |
| Recaps | ~23 |
| Tracking or positional data | 4 |
| Simulation or what-if | 4 |

- **"Receipts" is taken.** Several entries use near-identical taglines ("commentary with receipts", "prove every word"). We drop the word from product copy and the pitch; the rail is the **evidence rail**.
- **The rubric pays for execution.** Roughly 10% of the weight is idea novelty; the rest is code quality, deployment readiness, a balanced build and a clear demo. Judges need not watch past 2:00, so the video is designed shot by shot, not recorded at the end.
- **Weakness to fix:** the Checker → Narrator loop is the one genuinely agentic pattern, so it is shown on screen (AMENDED with the old wording struck through), not left in a log.
- **Nothing should look, sound or feel generated.** `docs/VOICE.md` sets the register, `voice/banned.yaml` is enforced in CI and in the evals, and `voice/examples.yaml` holds 15 Narrator examples adapted from real live text and published metric definitions (sources kept outside the repo because they name real clubs). No sparkle icons, gradients, typing animation or chat bubbles; no synthetic voiceover or stock music in the video.
- **Name kept.** Matchproof is fine; the "Match-" prefix is crowded, so the tagline carries the difference.

## Compliance gates

Stage One is pass/fail on theme fit and on reasonably applying the required technologies. Every row below is a release blocker: the submission does not go in until all are ticked. Source: [Official Rules](https://github.com/microsoft/insidethegamehackathon/blob/main/OFFICIAL%20RULES.md).

| Rule | Requirement | How we meet it | Verified by |
| --- | --- | --- | --- |
| 4.3 New projects only | Built after Sept 29, 2026 | Fresh public repo created Oct 17; no code copied from football-analytics or tylermartins.com | Repo creation date + commit history |
| 4.11 Original work, open source allowed | Open source deps OK if we build on them and respect licences | All code written in this repo during the hackathon, pitch and chart components included; only standard open-source libraries (D3, Next.js, FastAPI) as dependencies | Dependency licence list generated in CI to docs/compliance/ |
| 4.7 Synthetic data | Synthetic, football-realistic data only; no real match data or footage | Generator output only. Real data used solely to derive aggregate calibration targets, never shipped | Repo scan: no StatsBomb events committed; data/ README |
| 4.7 + 4.4 IP | No third-party trademarks, crests, real clubs or players, copyrighted music | Fictional clubs and players; no Premier League marks in UI or video; royalty-free or no music | Pre-submit checklist review |
| 4.4 Pitch | Short description: what, which Microsoft tech, what it does, problem solved | docs/PITCH.md, reused on the form | Copy pasted into form |
| 4.4 Video | Under 2 minutes, shows it running, public on YouTube or Vimeo | 1:50 cut, unlisted-public YouTube link | Duration checked before upload |
| 4.4 Repo | Public GitHub repo URL | github.com/tmartins14/matchproof, MIT licence | Opened in a logged-out browser |
| 4.8 Testing | Working demo link, free, no restriction, live until Nov 10 | Static Web App on Azure at matchproof.tylermartins.com, no login; live runs with the cached replay as the zero-model-call fallback | Uptime check scheduled through Nov 10 Partly met (Oct 25): the deployed desk at https://gray-sand-08c45ef0f.2.azurestaticapps.net answers with no login, `scripts/smoke_prod.sh` passes all 5 checks, and two availability tests (web root, API `/health`) from 3 regions every 5 minutes passed 72 of 72 runs in their first 2 hours. Not yet met: no live match has reached full time on the deployed pair, because the API container restarted twice mid-match (docs/DEPLOY.md, Known issue). Custom domain not set up. |
| 4.9 Language | All materials in English | English README, video, pitch; Spanish output is a feature, not a material | Review |
| 4.3 Functionality | Must run as shown in the video | Video recorded from the deployed URL, not localhost | Video source = prod URL |
| 6.1 Required tech | Reasonably applies the featured technologies | Foundry, Agent Framework, MCP, Azure AI Translator, Container Apps, Static Web Apps, App Insights | ARCHITECTURE.md service table Static Web Apps met (Oct 25): `infra/modules/staticwebapp.bicep` and `azd deploy web` serve the exported desk, and a live match streamed to it from the Container App (docs/screenshots/13/). |
| 1 Registration | Registered by Oct 20, 12 PM PT; Innovation Studio access | Registered; chase invite Monday if not received | Login confirmed |

## Scoring strategy

The five criteria are equally weighted, and ties break in criterion order, so Technological Implementation is the tiebreaker. Each criterion gets features built for it and evidence a judge can see without running anything.

| Criterion (20% each) | What we build for it | Evidence the judge sees |
| --- | --- | --- |
| Technological Implementation | Calibrated generator; schema-first contracts; typed Python, tests, CI; IaC with azd + Bicep; managed identity; hero tech in every stage | Calibration page; green CI badge; ARCHITECTURE.md service table; ADRs |
| Agentic Design & Innovation | Five agents with distinct roles sharing one match store; Checker-to-Narrator retry handoff; MCP server for match data; planted vs detected beats | Agent graph in README; an AMENDED and an OVERTURNED claim on screen with reasons; writer and judge on different models |
| Real-World Impact | Broadcast-ready timed overlay JSON; fact-checked narration a studio can air; fan, analyst and producer outputs from one graph | Overlay JSON schema; one-paragraph "who uses this Saturday" story in the pitch |
| UX & Presentation | The prototype screen, built for real: pitch overlays, evidence rail with review states, mode and language toggles, mobile layout; product text linted against VOICE.md | 1:50 video; live URL that opens straight into a replay |
| Category Adherence | Declared category: Best Enterprise Solution (reliability, transparency, controls) | Eval report, trace links, cost and rate limits, failure fallbacks documented |

**Category choice.** Declare Best Enterprise Solution. Verified claims are literally its "transparency and controls" language, and the scenario-harness framing answers its "clear path to enterprise adoption". Verification is crowded overall, but fewer entrants will chase this category than Multi-Agent. The design still meets every Multi-Agent test (distinct roles, shared state, handoffs, failure recovery) so judges can reassign us if they prefer, which rule 4.3 allows.

**Grand Prize angle.** Its description asks for the most complete solution with innovative use of the Microsoft AI stack. Completeness beats cleverness: a thin, finished, deployed pipeline outranks a deep, half-built one.

## Architecture

The seam rule holds end to end: Python computes, agents orchestrate and narrate, the browser only renders. The one contract everything depends on is the **claim graph**: claim → fact → event IDs, with a verdict on every claim.

&#91;embedded content: pipeline · 5 agents, 4 code stages, one shared store\]

The only loop is Checker back to Narrator, once per beat; after that a claim is blocked, not forced through.

### Agents and tools

| Component | Kind | Job | Hands off to |
| --- | --- | --- | --- |
| Composer | Agent (Foundry) | Turns a natural-language brief into a schema-valid MatchBrief: team dials, planted beats, seed | Generator tool |
| Generator | Python tool | Seeded possession-chain simulator; emits a full match (\~2,500 StatsBomb-shaped events) and honours planted beats; adds 5 Hz positions for all 22 players from a formation-anchored shape model, plus a freeze frame per event | Extractors |
| Extractors + beat detector | Python tools | Compute facts with provenance; detect candidate beats (high turnovers to shots, momentum swings, territorial spells, set-piece goals) | Producer |
| Producer | Agent (Foundry) | Ranks candidates into a 6 to 10 beat feed; marks each beat planted or detected | Narrator |
| Narrator | Agent (Foundry) | Writes claims per beat from a fact bundle only, never raw events; structured output with fact references | Checker |
| Checker | Deterministic reconciler + LLM judge (Claude Sonnet 5.5) | Verifies numbers in code, then judges support and runs the voice lint; verdict verified, rephrased or blocked (shown as STANDS, AMENDED, OVERTURNED); sends a beat back to Narrator once with reasons | Localizer |
| Localizer | Agent + Azure AI Translator | Builds fan, analyst and producer renderings; translates verified text; re-checks that every number survived translation | Claim graph store |
| match-data MCP server | MCP | Exposes get\_fact, get\_events and list\_beats to every agent; the only door to match data | All agents |

Shared state is one match store in Blob Storage: events, facts, beats and the claim graph, keyed by match ID and seed. Agents never pass data to each other directly; they read and write the store through MCP, which is what makes handoffs and retries traceable.

### Live mode and the brief

Live is the default path; the cached replay is the fallback. The brief asks for events ingested "as they happen" and output "responsive enough for live play", so the demo should run the pipeline for real rather than play back a finished graph.

- **Brief entry.** Two linked inputs. The Tactics panel (formation per team, three dials per team, storyline) is the canonical input to the generator: same tactics and seed, same match. The brief is the human-readable form of it. Changing tactics rewrites the brief deterministically from a template; editing the brief and pressing Read brief sends it to the Composer agent, which returns structured tactics the user can check and adjust. Randomize sets random tactics and rewrites the brief.
- **Streaming.** The generator emits a timed event stream; the API sends it to the browser over Server-Sent Events at a chosen speed (1×, 3×, 6× match minutes per second). SSE is simpler than WebSockets and runs on Container Apps without extra services.
- **Incremental compute.** Extractors update running stats per event. The beat detector fires when a pattern completes (a shot after a high turnover, a goal, a 15-minute territorial spell closing).
- **Verification in the open.** Each detected beat goes to Narrator then Checker asynchronously. Claims appear on screen as CHECKING, with the pitch highlighting the evidence, and resolve to STANDS, AMENDED or OVERTURNED. Latency budget: 8 s per beat at the 90th percentile, measured in the eval run.
- **Degrade, don't fail.** If a model call times out or the daily token cap trips, the run continues with code-only stats and the claim shows HELD. If the API is unreachable, the site offers the cached replay. Judges can always see something working.
- **Cost guard.** One live run is about 8 beats × 2 agent calls; a per-IP limit and a daily cap keep judging traffic predictable.

### Azure services

| Stage | Service | Why it is there |
| --- | --- | --- |
| Models + agents | Microsoft Foundry (project, model deployment, Agent Service, tracing) | Hero tech; one place for prompts, evals and traces |
| Orchestration | Microsoft Agent Framework (Python) | Sequential workflow with a Checker → Narrator loop |
| API + MCP server | Azure Container Apps | Scales to zero; one image serves the API and MCP endpoints |
| Storage | Azure Blob Storage | Match store and pre-computed claim graphs |
| Languages | Azure AI Translator | Deterministic translation of already-verified text |
| Front end | Azure Static Web Apps | Next.js + D3 components built in this repo, served without a login |
| Observability | Application Insights (OpenTelemetry) | One trace per pipeline run, linked from Producer mode |
| Secrets + identity | Managed identity, Key Vault | No keys in code or config |

### Repo layout

```
matchproof/
  schemas/            JSON Schema: Event, MatchBrief, Fact, Beat, Claim, ClaimGraph, Overlay
  packages/sim/       generator + calibration targets
  packages/intel/     extractors, fact registry, beat detector
  packages/agents/    composer, producer, narrator, checker, localizer, workflow
  packages/mcp_match/ MCP server over the match store
  services/api/       FastAPI: serve graphs, POST /compose (rate-limited)
  apps/web/           Next.js replay desk; viz/ holds pitch, overlay and momentum components built from scratch
  evals/              golden matches, adversarial claims, eval runner
  infra/              azure.yaml + Bicep
  docs/               SPEC, ARCHITECTURE, ADR/, CALIBRATION, DEMO, PITCH
```

## Engineering and AI practices

The loop is your WORKFLOW.MD, unchanged: you own Plan and Review, Claude Code owns Execute and Verify, and nothing reaches main without a PR you merged.

### Delivery

- **One task, one branch, one PR**, sized to an anchor hour. main is protected (enforce admins, required checks) from the first commit.
- **Schema first.** JSON Schemas land on day 1 and generate Pydantic models and TypeScript types, so the browser and the agents cannot drift apart.
- **ADRs for every irreversible choice** (category, model, orchestration framework, storage), one page each in docs/ADR/.
- **Every PR carries evidence**: the verification signal's output and an omissions list (4a and 4b in your loop). Visual PRs carry a screenshot from the deployed preview, since a green build has not been proof of a correct screen.
- **GitHub Copilot code review** runs on every PR as a second reviewer. It is cheap, it is on the hero list, and the README says honestly where it was used.

### Quality gates in CI (GitHub Actions)

| Gate | Tool | Blocks merge when |
| --- | --- | --- |
| Lint + types | ruff, mypy --strict, tsc | Any error |
| Unit + contract tests | pytest, schema validation on fixtures | Any failure |
| Generator determinism + calibration | pytest over 4 seeds | A metric leaves its target band |
| Grounding evals | evals/ runner on 3 golden matches | Any published claim lacks a fact reference, or any number fails reconciliation |
| Checker recall | 30 adversarial claims (wrong numbers, season data, invented positions) | Fewer than 28 caught |
| Translation integrity | Number and name invariance EN → ES | Any mismatch |
| Web build | next build + Playwright smoke on the replay screen | Build or smoke failure |
| Deploy | azd provision + deploy on merge to main | Health check fails |

Model-calling evals run on PRs that touch prompts or agents and nightly, not on every commit, to keep cost down.

### AI engineering

- **Facts-only context.** The Narrator sees a fact bundle, never raw events, so it has nothing to invent from.
- **Code before judgement.** Number reconciliation is deterministic Python; the LLM judge only decides whether wording stays inside the fact.
- **Structured outputs everywhere**, validated against the schemas; an invalid response is a retry, then a template fallback, never a crash.
- **Prompts are versioned files** with the model deployment pinned in config; any change re-runs the eval suite.
- **Bounded loops.** One Checker → Narrator retry per beat, with timeouts; after that the claim is blocked, not forced through.
- **Foundry content filters on** and a short responsible-AI note in the README.

### Operations and cost

- One OpenTelemetry trace per pipeline run, shipped to Application Insights and linked from Producer mode.
- The public site serves pre-computed claim graphs, so judging costs nothing. Live Compose sits behind a per-IP rate limit and a daily token cap, and degrades to cached matches when either trips.
- An Azure budget alert set on day 1; Container Apps scale to zero.

### Design process

Oct 23: design pass done on Friday. One theme, Floodlight; see `docs/DESIGN.md`. Editorial deferred (ADR 0006 addendum).

The product ships two themes the viewer switches between, replacing light and dark mode: Broadcast (dark, condensed type, built for overlays on footage) and Editorial (your brand: cream, Fraunces, crimson and navy). Both read from one token file, so every component is built once. The prototype's Broadcast pass is a placeholder until this process runs on Saturday Oct 24; Editorial reuses your existing palette and type.

1. **References first (Friday, train).** Screenshot 5 to 10 you like: Sky Sports or ESPN on-screen graphics, The Athletic, FotMob, Opta graphics, F1 TV timing towers. Study them for structure, never copy palettes, marks or the Premier League's own package.
2. **Hallmark study** on the references to extract layout structure, type pairing and colour anchors into a DESIGN.md.
3. **Edit DESIGN.md by hand** to lock the broadcast basics: condensed display type, tabular numbers, dark canvas with team-colour accents, scorebug and lower-third components, dense data layouts instead of airy cards, and the verdict stamp as the one signature element.
4. **Build with Impeccable in Claude Code.** Use typeset and bolder while building; run critique and `npx impeccable detect` before any screen is accepted.
5. **Accessibility review** (Design plugin) on contrast and focus states, since a dark theme fails contrast most often.

Third-party skills are code that runs in your environment: read each SKILL.md and any scripts before installing. Skip catalogue-driven style pickers; they are a main source of look-alike AI interfaces. Without strong references, every one of these tools drifts toward generic SaaS.

## Schedule

Oct 26 and 27 are off at about 10 hours each: 57 hours in total. Weekdays before that are 3 hours, so the core pipeline is built in thin daily slices and the two days off go to features, quality and the video. Estimates assume Claude Code writes the code and you spend your time on specs, review and judgement. Each day ends with a gate; a missed gate triggers the cut list that evening.

| Day | Hours | Build | Gate (pass/fail) |
| --- | --- | --- | --- |
| Sat Oct 17 | 1 | This plan; repo created and protected; clarification email to organisers | Plan approved; repo exists with branch protection |
| Sun Oct 18 | 7 | SPEC, ARCHITECTURE, first ADRs; all JSON Schemas; scaffold; CI; azd + Bicep for Foundry, Container Apps, Blob, App Insights; hello-world deployed | **M1 walking skeleton**: CI green; a Container App calls a Foundry model with managed identity |
| Mon Oct 19 | 3 | Voice guide, banned-pattern lint and sourced Narrator examples (prompt 02.1); generator: possession chains, team dials, pass quality and speeds, seeded output, planted goals, timed event stream (prompt 03) | Voice lint in CI; 4 seeds schema-valid and deterministic |
| Tue Oct 20 | 3 | Calibration tests; 22-player position layer (formation shape shifted by ball and team dials, 5 Hz, freeze frame per event); extractors with provenance, batch and incremental, including positional facts (line height, compactness, distance between lines) for the hero claim. Confirm registration before 12 PM PT (3 PM ET) | **Generator done**: every calibration metric inside its band |
| Wed Oct 21 | 3 | Beat detector (live and batch); MCP server; SSE endpoint that streams a match at a chosen speed | A curl of the stream shows events, facts and beats arriving on time |
| Thu Oct 22 | 3 | Narrator (gpt-5-mini) and Checker with Claude Sonnet 5.5 judge on Foundry; number reconciler; voice lint in the Checker; retry loop; eval runner + adversarial set. First draft of the video beat sheet (train) | Checker catches 28 of 30 adversarial claims; one beat verified in under 8 s |
| Fri Oct 23 | 3 | Composer with randomize, including custom planted moments from free text (a `custom` storyline with validation: at most 6 moments, windows inside the match, final score derived from planted goals); Producer; full workflow; claim graph to Blob; tracing. Collect 5 to 10 design references on the train | **M2 pipeline complete**: brief in, live claims out, one trace per run |
| Sat Oct 24 | 7 | Design system: hallmark study on references, hand-edited DESIGN.md, tokens. Chart primitives from scratch, including the 22-player layer and freeze frames. Live desk wired to SSE; deployed to Static Web Apps | **M3 live end to end on Azure**: kick off a match on the live URL and watch claims get checked — **claimed Oct 26, 00:34 UTC (8:34 PM ET, Oct 25)**: one match played from the desk on the deployed URL at 6x with agents reached full time, 2 to 0 at 98:04, with 13 claims checked (`docs/screenshots/13/m3-full-time-desk.jpg`; caveats in `docs/DEPLOY.md`, Known issue) |
| Sun Oct 25 | 7 | Evidence rail with CHECKING, STANDS, AMENDED and OVERTURNED states and the evidence highlight on the pitch; fan, analyst and producer modes; Moments editor in the Tactics panel (add a red card, goal or penalty by side and minute, about 1 to 1.5 h); Localizer (EN, ES); cached replay as the fallback path; 3 pre-generated matches | Live and cached paths both work on the live URL |
| Mon Oct 26 (off) | 10 | Realistic movement first (committed); add-backs below; evals in CI; impeccable critique and detect on every screen; bug bash on phone and laptop; accessibility pass | **M4 feature freeze** at 8 PM: nothing new after this |
| Tue Oct 27 (off) | 10 | Fresh-eyes review by a separate agent; fixes only; README, DEMO.md, testing instructions; record and cut the video; pitch; submission form; tag v1.0; uptime check to Nov 10 | **M5 submitted by 9 PM ET** |

Weekday hours assume both train anchor hours plus 30 minutes of evening review. If a weekday delivers less, the slack comes from the Monday Oct 26 add-backs, never from Monday's bug bash.

**Monday Oct 26 add-backs, in order of score per hour.** Each is small once the core works, and each maps to words in the brief or a judging criterion:

1. **Broadcast overlay route (2 h).** A transparent 1920×1080 page that plays only the timed overlays, ready to key over a feed in OBS or vMix.
2. **Favourite-club, player-focus and single-metric modes (2.5 h).** All three are named in the brief.
3. **French and Portuguese (1 h).** Nearly free once Spanish works, because the invariance check is language-agnostic.
4. **Audio-described mode with Azure AI Speech (3 to 4 h).** Reads only claims that STAND, for viewers who can't check the screen. Verification matters most when the audience can't see the evidence. Only if the core is on schedule.
5. **Realistic movement (4 to 6 h**, committed, never cut). First block on Monday. Swap the shape model for role-based movement (hold slot, press when nearest, make runs, track runners), with the passer and shooter pinned to each event location and with speed and acceleration limits, behind the same 5 Hz position format so nothing downstream changes.
6. **Fabric audit sink (stretch, 3 h).** Every claim and verdict lands in a Fabric lakehouse. Cut it first: Fabric setup is the least predictable task in the plan.

The risk in this shape is that the core lands late, on thin weekdays. If M2 slips past Friday, Saturday absorbs it and the add-backs shrink, not the bug bash or the video.

## Cut list, risks and mitigations

If a gate slips, cut from the top of this list down. Never cut the evidence rail and its review states, the Checker, the evals, or deployment: those are the entry.

1. Azure AI Speech narration (never in scope unless everything else is done)
2. Live Compose button: ship cached matches only
3. Player-focus mode
4. Moments editor in the UI (the four preset storylines and the Composer still cover custom moments)
5. Producer agent: rank beats in code instead
6. Third pre-generated match
7. Composer agent: hand-write the MatchBrief JSON (last resort: it weakens the agentic story)

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Innovation Studio invite never arrives | Medium | Cannot submit | Check spam; email organisers Monday Oct 19; screenshot registration confirmation |
| Chart components built from scratch take longer than planned | Medium | Replay desk slips into Saturday | Build only four primitives (pitch, marker, line, strip); review them on the fixture page Tuesday before any wiring |
| StatsBomb terms forbid deriving calibration targets | Low | Weaker calibration story | Ship only aggregate ranges with attribution; fallback to published public ranges |
| Foundry model quota or region gap | Low (was Medium) | Judge stays on gpt-5-mini | Claude quota approved Oct 19 (80K TPM shared); smoke-test `checker-judge` before Thursday; gpt-5-mini judge remains the fallback |
| Output reads as AI-generated | High | Presentation and trust scores drop | VOICE.md, banned-pattern lint in CI and evals, sourced few-shot examples, no AI-coded UI |
| Crowded verification field | High | Entry blends in | Lead with the controllable match and positional claims; video opens on an OVERTURNED claim |
| Agent Framework learning curve | Medium | Thursday slips | Timebox 2 hours; fallback to the Foundry Agent Service SDK with the same roles |
| Generator rabbit hole | High | Eats Wednesday | Hard stop at the Tuesday calibration gate |
| Visual bugs pass CI | High | Judge sees a broken screen | Playwright screenshot per PR; Monday bug bash on a real phone |
| Push before review | Medium | Unreviewed code on main | Branch protection plus required checks; no admin bypass |
| Demo goes down during judging | Low | Fails rule 4.8 | Static pre-computed path; budget alert; uptime check through Nov 10 |
| Cost overrun | Low | Surprise bill | Daily token cap, scale to zero, budget alert |

## Submission package

Judges may score on the video and text alone (rule 4.8), so the video carries the entry. Target 1:50; anything past 2:00 may go unwatched.

| Time | Shot | What it proves |
| --- | --- | --- |
| 0:00–0:08 | Cold open, no title card: a positional claim goes CHECKING, the pitch highlights the back line, the claim is OVERTURNED and an AMENDED version appears | The core idea, in the first seconds |
| 0:08–0:20 | One line on the problem: one wrong stat on air and the tool gets switched off | Real-world impact |
| 0:20–0:45 | Same seed, two press settings: two visibly different matches, both narrated and checked live | Controllable match, synthetic data, UX |
| 0:45–1:05 | The scenario harness: the eval report (claims caught out of 30), the trace link, writer and judge on different models | Enterprise controls, agentic design |
| 1:05–1:20 | Fan mode in Spanish; analyst mode on the same beat | Personalisation, multi-language |
| 1:20–1:40 | Calibration page; planted vs detected beats | Data innovation |
| 1:40–1:50 | Architecture: the Azure services in use; repo and live URL | Tech implementation |

Recorded in your own voice, in one sitting, from the deployed URL; real speed except one labelled 6× section; cursor visible; no music. You write the spoken lines from this beat sheet.

Alongside the video:

- [ ] **Pitch** (docs/PITCH.md): what we built, Microsoft technologies used, what it does, the problem it solves, in about 150 words. You write the first draft; Claude tightens it and runs a humanizer pass; you read it aloud and cut anything you wouldn't say. Concrete numbers, no superlatives, first person
- [ ] **README**: one-line pitch, live URL, video link, agent graph, service table, "how to run locally", eval results, honest notes on where Copilot and Claude Code were used
- [ ] **DEMO.md testing instructions**: open the URL, press Replay, click any sentence, switch to Producer, switch to Spanish; no login needed
- [ ] **Compliance folder**: clarification replies, data statement, licence notes
- [ ] Video recorded from the deployed URL, no copyrighted music, captions on

## Next actions

- [x] Plan approved; repo created and protected; M1 walking skeleton deployed (Oct 18)
- [x] Innovation Studio access; field review done (Oct 19)
- [x] Claude quota approved (Oct 19)
- [ ] Merge this docs update, then run prompt 02.1 (voice), then prompt 03 (generator)
- [ ] Smoke-test a `checker-judge` deployment of Claude Sonnet 5.5 (US Data Zone if offered) and check the budget alert
- [ ] Read the 15 Narrator examples on the train; rewrite or delete any you wouldn't say aloud
- [ ] Delete `rg-matchproof-sandbox` if it still exists
- [ ] Still open: organiser reply on deriving calibration ranges from public open data
