# Matchproof — Architecture

Python computes, agents orchestrate and narrate, the browser renders. The contract everything depends on is the **claim graph**: claim → fact → source IDs, with a verdict on every claim.

## Pipeline

```
Tactics / brief ──► Composer ──► MatchBrief
                                    │
                                    ▼
                         Generator (seeded, Python)
                    events + 5 Hz positions + freeze frames
                                    │ SSE stream at 1× / 3× / 6×
                                    ▼
                 Extractors + beat detector (incremental, Python)
                        facts with source IDs, candidate beats
                                    │
                                    ▼
                    Producer ──► Narrator ──► Checker ──┐
                                    ▲          (retry once) │
                                    └───────────────────────┘
                                    │ verdicts
                                    ▼
                         Localizer (modes, EN/ES)
                                    │
                                    ▼
                    Claim graph + overlay JSON ──► Live desk
```

All agents read and write one match store through the `match-data` MCP server. They never pass data to each other directly, which makes every handoff and retry traceable.

## Components

| Component | Kind | Input | Output |
| --- | --- | --- | --- |
| Composer | Agent | Free-text brief | `MatchBrief` (schema-valid) |
| Generator | Python | `MatchBrief` | `Event[]`, `PositionFrame[]` at 5 Hz, freeze frame per event |
| Extractors | Python | Events, frames | `Fact[]`, each with `source_ids` |
| Beat detector | Python | Facts, events | Candidate `Beat[]`, marked planted or detected |
| Producer | Agent | Candidate beats | Ranked feed of 6 to 10 beats |
| Narrator | Agent | One beat's fact bundle | Draft `Claim[]` with `fact_ids` |
| Checker | Python reconciler + LLM judge | Draft claims, facts | Verdict per claim; one retry to Narrator with reasons |
| Localizer | Agent + Azure AI Translator | Verified claims | Fan, analyst and producer renderings; EN and ES; number invariance check |
| Renderer | Python | Beat, events, frames | `Overlay` JSON, timed to the match clock |
| match-data MCP | MCP server | Tool calls | `get_fact`, `get_events`, `get_frame`, `list_beats`, `put_claims` |

## Tactics and the brief

The Tactics object inside `MatchBrief` (formation and press, directness and line height per team, plus a storyline) is the canonical generator input. Same tactics and seed produce the same match.

- Tactics → brief: deterministic template, in code.
- Brief → tactics: the Composer agent returns structured tactics; the UI shows them for the user to confirm or adjust.
- Randomize: random tactics, then the template writes the brief.

## Live mode

- The API streams the generator's output over Server-Sent Events: `event`, `frame` (5 Hz), `fact`, `beat`, `claim` and `verdict` messages.
- Extractors run incrementally per event. The beat detector fires when a pattern completes.
- Each beat is narrated and checked asynchronously. The UI shows claims as Checking, then flips them to a verdict.
- Budget: 8 s per beat at p90 from detection to verdict.
- Degrade, don't fail: a model timeout or a tripped token cap shows "verification delayed" and keeps the match running. If the API is unreachable, the site offers the cached replay.

## Player positions

- Contract: `PositionFrame` at 5 Hz for 22 players plus the ball, and a freeze frame attached to every event.
- Version 1 (Tue Oct 20): formation shape model. Each player has a slot; the shape shifts with the ball and the team's line-height dial.
- Version 2 (Mon Oct 26, committed): role-based movement. Hold slot, press when nearest (scaled by press dial), make runs in possession (scaled by directness), track runners. Speed and acceleration caps. The passer, receiver and shooter are pinned to each event's location so frames and events never disagree.
- Positional claims (for example "players ahead of the ball") are computed from freeze frames and checked like any other fact.

## Azure services

| Stage | Service | Why |
| --- | --- | --- |
| Models and agents | Microsoft Foundry (project, model deployment, Agent Service, tracing) | Hero technology; prompts, evals and traces in one place |
| Orchestration | Microsoft Agent Framework (Python) | Sequential workflow with a Checker → Narrator loop |
| API and MCP server | Azure Container Apps | Scales to zero; serves SSE and MCP |
| Storage | Azure Blob Storage | Match store and cached claim graphs |
| Languages | Azure AI Translator | Deterministic translation of already-verified text |
| Front end | Azure Static Web Apps at matchproof.tylermartins.com | No login; custom domain with managed TLS |
| Observability | Application Insights (OpenTelemetry) | One trace per run, linked from Producer mode |
| Identity and secrets | Managed identity, Key Vault | No keys in code or config |
| Audit (stretch) | Microsoft Fabric lakehouse | Every claim and verdict, queryable |

## Contracts

Schemas live in `schemas/`. Python models and TypeScript types are generated from them.

| Schema | Holds |
| --- | --- |
| `match_brief` | Seed, tactics for both teams, storyline, planted beats |
| `event` | One match event, absolute 120 × 80 coordinates |
| `position_frame` | 22 players + ball at one instant |
| `fact` | One computed value with its source IDs and the extractor that produced it |
| `beat` | One key moment, planted or detected, with its fact IDs |
| `claim` | One sentence, its fact IDs, verdict, draft and reason |
| `overlay` | Timed drawing instructions for one beat |
| `claim_graph` | Everything above for one match, as served to the desk |

## Themes

Two themes from one token file: **Broadcast** (dark, condensed display type, made for overlays on footage) and **Editorial** (cream, Fraunces and Geist, crimson and navy). Components read tokens only; no hard-coded colours.
