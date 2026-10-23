# Build prompt 09 — Agent workflow, Producer and live claims

**Mode:** code. **Budget:** about 3.5 hours. **Branch:** `feat/workflow-live-claims`. **Depends on:** prompt 08.2 (PR #18) merged.

## Part 0 — Two deterministic fixes from the 08.2 review (first commit)

1. **Evaluative adjectives.** The v2 judge still passes "a brilliant finish", "a tidy finish" and "shielding their goal". Add narration `error` rules to `voice/banned.yaml` for `brilliant`, `tidy`, `superb`, `clinical`, `stunning`, `sublime`, `wonderful` and `shielding`. They reach the Checker through the voice-lint step. Re-check that the 15 lines in `voice/examples.yaml` still lint clean.
2. **Card bundles.** A red-card beat's bundle currently includes the foul's freeze-frame box counts (zone attackers and defenders), and the Narrator wrote about "defenders in the box at the set piece". In `get_beat_bundle`, card beats include card, player and minute facts only, plus the players-after count, and no freeze-frame zone facts. Add a test.

## Context

Read:
- `CLAUDE.md`, `docs/VOICE.md`
- `docs/ARCHITECTURE.md` (agents table, live mode, MCP), `docs/adr/0002-foundry-and-agent-framework.md`, `docs/adr/0008-mcp-read-only-public-writes-internal.md`
- `packages/agents/src/agents/pipeline.py`, `checker.py`, `narrator.py`
- `services/api/src/api/live.py`, `matchdata.py`
- `schemas/stream_message.schema.json`, `schemas/claim.schema.json`

This task makes the agents a real multi-agent workflow and puts their output on the live stream:
- **Producer** decides which beats get narrated, and in what order.
- **Narrator** writes.
- **Checker** verifies, with the bounded retry to the Narrator.
- **Microsoft Agent Framework** orchestrates.
- **The internal MCP server** is the agents' only way to reach match data.

After this task the live stream carries claims with verdicts. That is milestone M2: brief in, live claims out, one trace per run.

**One design point to preserve: verify before air.** The pipeline runs 120 match seconds ahead of playback. So a beat's claims are usually narrated and checked **before the viewer reaches that moment**, like a broadcast delay. Nothing unverified reaches the screen. If a check isn't finished when the moment airs, the claim shows as `checking`, then gets its verdict when ready. Never fake a delay, and never show a verdict before the check has actually finished.

Before writing: restate the task back in ten lines or fewer. Include:
- the workflow graph and its one loop,
- the Producer's hard rules versus its judgement,
- exactly when `claim` and `verdict` messages go out relative to playback.

Then wait for my go.

## Seam rules

- Agents reach match data only through the internal MCP server (`get_beat_bundle`, `list_beats`, `put_claims`). No agent imports the store or the registry.
- The Producer's hard rules are code; the model only judges inside them.
- Prompts are versioned files, deployments come from `models.yaml`, no keys.

## Parts

1. **Agent Framework workflow (`agents/workflow.py`).**
   - Build the graph with the Microsoft Agent Framework Python SDK: **Producer → Narrator → Checker**, with one conditional edge **Checker → Narrator** carrying the reasons, taken at most once per claim. The outcome must match `pipeline.py`'s verdicts exactly; reuse its reconciler, lint and judge code as tools or steps rather than duplicating them.
   - Agents use the internal MCP server through the framework's MCP tool support, connected in process or over a local transport. It is never exposed on the network.
   - **Timebox:** if the framework's MCP or workflow support costs more than about 90 minutes, fall back to the Foundry Agent Service SDK, or a thin hand-written orchestrator with the same graph, as ADR 0002 allows. Record what happened in the ADR.
   - Keep `narrate_and_check` as a thin wrapper over the workflow so evals keep working, and re-run `make evals` to confirm parity: same counts as 08.2.
2. **Producer (`agents/producer.py`, prompt `agents/prompts/producer.v1.md`).** Runs live, beat by beat. For each detected beat it returns `{narrate: bool, priority: 1–5, note: str}`, where `note` is one short line for the Producer-mode log, written by `VOICE.md` rules.
   - **Hard rules in code:**
     - always narrate goals, red cards and follow-up `momentum_swing` beats;
     - a per-match narration budget, `NARRATION_BUDGET = 12`;
     - no two narrated beats of the same kind within 3 match minutes, except goals.
   - **Model judgement within those rules:** salience, variety, and whether a beat adds anything new given the beats already narrated. It gets the beat, its salience, and a one-line summary of beats narrated so far.
   - Set `rank` on narrated beats (1 = first in the feed).
3. **Live wiring (`live.py`).**
   - When the detector emits a beat (in the lookahead), submit it to the workflow on a bounded worker pool (`MAX_CONCURRENT_BEATS = 3`).
   - When playback reaches the beat, send the beat's facts and the beat itself (as now), then its claims:
     - each claim whose check finished is sent as a `claim` message with its final verdict and `checker.latency_ms`;
     - a claim still being checked is sent with verdict `checking`, then a `verdict` message as soon as the Checker finishes.
   - A beat the Producer skipped is still streamed (the feed can show it as unnarrated), with no claims.
   - **Degrade, don't fail:**
     - model errors or timeouts make the claim `delayed`, and the match keeps playing;
     - if the workflow is down entirely, beats stream without claims and a `status` message says verification is unavailable.
4. **Independent auditor (`agents/auditor.py`), log-only.** A second-vendor check that never delays the screen.
   - After the Checker settles a claim (`verified` or `rephrased`), submit it to the auditor on its own bounded pool (`MAX_CONCURRENT_AUDITS = 2`). The auditor runs the same judge rubric (`judge.v2.md`) on deployment `judge-grok`, set as role `auditor` in `models.yaml`, with `AUDIT_TIMEOUT_S = 45`.
   - **Record:** `agree` or `disagree` with the problem category and reason, or `unavailable` (on 429s and timeouts, retry once and then give up quietly). Store it with the claim, under a new optional `audit` object in `claim.schema.json` (`deployment`, `outcome`, `problem`, `reason`, `latency_ms`; run `make gen`). Write it through the internal MCP server.
   - **Never changes a published verdict** in this version. A disagreement goes to the Producer log (one plain line), the trace (an `audit` span linked to the claim's span), and a per-match audit summary.
   - **Stream:** an `audit` result for a claim already on screen is sent as a `verdict` message carrying the same verdict plus the `audit` object, so the UI can show "audited by a second model" later. Add nothing else to the screen.
   - **Summary:** `GET /matches/{match_id}/audit` returns claims audited, agreement rate, disagreements with reasons, and unavailable count. `evals/e2e.py` adds the audit summary to its report.
   - **Cost:** audit tokens count toward `DAILY_TOKEN_CAP`. When the cap trips, auditing stops first, before narration.
   - **Docs:** add the auditor to the agents table and the workflow diagram in `ARCHITECTURE.md`. Add an ADR 0002 Decision-log line: inline judge `gpt-5-mini` for latency, independent auditor `judge-grok` for a second vendor, log-only, with the bake-off numbers as the reason.
5. **Cost guard.** A process-wide daily token counter, `DAILY_TOKEN_CAP = 2_000_000`, read from the environment. When it trips, new beats are streamed without narration and a `status` message says narration is paused for the day. Expose current usage at `GET /health/budget`.
6. **Tracing.**
   - One OpenTelemetry trace per match run, and a child span per beat workflow, with spans for Producer, Narrator, reconcile, lint, judge and retry. Agent Framework spans nest under ours where the framework emits them.
   - Put the trace id in `claim.checker.trace_id`, and give each claim's `verdict` message the beat's span id.
   - Locally, export to the console; in Azure, export to Application Insights (already configured).
   - Add a "Find a match's trace" snippet to `docs/DEPLOY.md`, with the KQL query for App Insights.
7. **Docs:** update the agents table and live-mode section in `docs/ARCHITECTURE.md`, including **verify before air**. Add the workflow graph as a small Mermaid diagram.

## Tests (CI, no model calls; fake LLM clients)

- **Workflow equals pipeline:** for the same fake responses, the workflow and `narrate_and_check` produce identical claims and verdicts. The retry edge is taken at most once.
- **Producer hard rules:**
  - goals, red cards and follow-ups are always narrated, even if the fake model says no;
  - the budget caps narrations at 12;
  - the same-kind spacing holds;
  - ranks are 1..n with no gaps.
- **Stream ordering:**
  - a claim is never sent before its beat;
  - a `verdict` never comes before its `claim`;
  - claims checked before air are sent with their final verdict;
  - a slow fake judge produces `checking` then `verdict`.
- **Degradation:** a failing fake model gives `delayed` claims and the match finishes; tripping the token cap gives the paused status and no further model calls.
- **Agents never touch the store:** a test asserts the `agents` package doesn't import `mcp_match.store` or `intel.registry`.
- **Trace ids:** every claim carries a trace id.
- **Auditor:**
  - a fake auditor that disagrees never changes the published verdict, and the disagreement appears in the Producer log and the audit summary;
  - a fake 429 gives `unavailable` after one retry;
  - audits never delay a claim message (assert claim timing with a slow fake auditor);
  - auditing stops before narration when the token cap trips.
- **Part 0:** the new adjective rules fire, and card bundles carry no zone facts.

## Verification signal (show the output)

1. `make lint typecheck test` exits 0; CI green.
2. `make evals` summary unchanged from 08.2.
3. A `curl -N` excerpt of a local stream (`red_card_flip` seed 3, speed 3, real models) around the red card: the beat, then its claims with verdicts.
4. The Producer log for that match: narrated and skipped beats with their notes.
5. The span tree for one beat from the console exporter.
6. Totals for one full match: model calls, tokens, cost estimate, split by Narrator, judge and auditor.
7. The audit summary for that match: agreement rate, plus each disagreement with both judges' reasons.

## Omissions list (required in the PR)

Agent Framework features tried and abandoned; anything that only worked with fake clients; token use per match.

## Out of scope

Composer, custom moments and Blob persistence (prompt 10, Saturday morning), the web UI, Spanish, `azd up` (Tyler runs it after merge).
