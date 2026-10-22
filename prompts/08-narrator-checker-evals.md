# Build prompt 08 — Narrator, Checker and the judge bake-off

**Mode:** code. **Budget:** about 3 hours. **Branch:** `feat/narrator-checker`. **Depends on:** prompt 07 merged.

## Context

Read:
- `CLAUDE.md`, `docs/VOICE.md`, `voice/banned.yaml`, `voice/examples.yaml`
- `docs/ARCHITECTURE.md` (agents table, MCP), `docs/adr/0002-foundry-and-agent-framework.md` (Decision log), `docs/adr/0008-mcp-read-only-public-writes-internal.md`
- `schemas/claim.schema.json`, `schemas/claim_graph.schema.json`, `schemas/common.schema.json`
- `packages/agents/src/agents/llm_client.py`, `packages/intel/src/intel/voice_lint.py`, `packages/intel/src/intel/display.py`
- `packages/mcp_match/src/mcp_match/server.py`, `services/api/src/api/matchdata.py`

This task builds the two agents at the centre of the product.
- **Narrator:** turns one beat's fact bundle into one to three short claims.
- **Checker:** reconciles every number in code, runs the voice lint, then asks an LLM judge whether the wording stays inside the facts. It returns `verified`, `rephrased` or `blocked`, with one retry to the Narrator.

It also builds the eval runner that picks the judge model by measurement, and adds a decision-log entry to ADR 0002.

**Models (already deployed in Foundry resource `ais-oou4h3al`):**

| Role | Deployment | Model |
| --- | --- | --- |
| Narrator | `gpt-5-mini` | OpenAI gpt-5-mini |
| Judge candidate | `judge-mai` | Microsoft MAI-Thinking-1 |
| Judge candidate | `judge-grok` | xAI grok-4.7 |
| Judge fallback | `gpt-5-mini` | Separate prompt; only if neither candidate qualifies |

Claude was the planned judge. Its Marketplace deployment failed twice with `MarketplaceSubscriptionCannotBeCompleted`, and a support request is open.

Before writing: restate the task back in ten lines or fewer. Include:
- how a claim moves through Narrator → reconciler → voice lint → judge → retry,
- what the reconciler accepts as a match for a number,
- how the bake-off picks the judge.

Then wait for my go.

## Seam rules

- The Narrator receives a beat's fact bundle (from `get_beat_bundle` on the internal MCP server), never raw events. It may state only numbers that appear in a cited fact's display renderings.
- **Code before judgement.** Number reconciliation and the voice lint are deterministic Python and run before any judge call. The judge never sees a claim that failed reconciliation; that claim is rephrased by retry or blocked.
- Prompts are versioned files. Model deployments live in config, not code. No keys: managed identity and `az login` only.

## Part 0 — MCP fixes from Wednesday's Azure test

1. **Stop the inspector hang.** The public server is stateless, but it holds `GET /mcp` open, which stalls the MCP Inspector's other requests. Return **405** with an `Allow: POST` header for `GET` and `DELETE` on `/mcp`. **Test:** a `GET` returns 405 at once.
2. **No spoilers on the public endpoint.**
   - `MatchStore` tracks each live match's **playback position**: the match time last sent to viewers.
   - The public (read-only) server returns only events, facts and beats at or before that position.
   - The internal server keeps the full lookahead.
   - A finished match exposes everything.
   - **Test:** mid-stream, public `list_beats` omits a beat the internal server already has.

## Schema change (first commit after Part 0)

Claim ids follow beat ids. Change `claimId` in `common.schema.json` to accept `cl-` + the beat id without its `bt-` prefix + `-NN` (for example `cl-001484-card-01`), still accepting the old form. Run `make gen`.

## Parts

1. **Config: `packages/agents/config/models.yaml`.** Roles `narrator`, `judge` and `judge_candidates`, each with deployment name, max output tokens, timeout and temperature where supported. The active judge is set here and overridable by environment variable (`JUDGE_DEPLOYMENT`). `llm_client.py` gains `client_for(role)`. All deployments share the resource's OpenAI-compatible `/openai/v1` endpoint and the same Entra token. **Verify early that `judge-mai` and `judge-grok` answer through that endpoint**, and record any that need a different route.
2. **Structured output.** A helper that asks for JSON matching a Pydantic model:
   - use `response_format` JSON schema where the deployment supports it, and JSON mode otherwise;
   - validate, and on invalid output retry once with the validation error appended;
   - then raise.
3. **Narrator (`agents/narrator.py`, prompt `agents/prompts/narrator.v1.md`).**
   - **Inputs:** the beat bundle, `mode` (`fan`, `analyst` or `producer`) and `lang` (`en` only for now; the Localizer comes Sunday).
   - **Prompt:** the register from `VOICE.md`, plus few-shot examples built programmatically from `voice/examples.yaml`, picking 4–6 matching the beat kind and mode (always including one AMENDED pair as a "don't" example).
   - **Output:** one to three claims, each with `text` (30 words or fewer) and the `fact_ids` it relies on.
   - Accepts an optional `revise` input: a previous draft plus the Checker's reasons, for the one retry.
4. **Reconciler (`agents/reconcile.py`, pure Python).**
   - For each claim, find every number token with `intel.voice_lint.numbers_in`, and match it against the display renderings (`en`) of the claim's cited facts.
   - A match is an exact rendering, or the rendering's numeric part with the same unit word.
   - Fill `claim.numbers` with `as_written` and `fact_id`. Any number with no matching cited fact fails reconciliation, with the reason naming the number.
   - Citing a fact id not in the bundle also fails.
5. **Checker (`agents/checker.py`, judge prompt `agents/prompts/judge.v1.md`).** Order:
   1. reconcile;
   2. voice lint (error-level rules fail);
   3. judge.

   **The judge** gets the claim and only its cited facts' names, values and renderings. It answers JSON `{supported: bool, problem: "overclaim" | "unsupported_cause" | "wrong_entity" | "wrong_time" | "outside_knowledge" | null, reason: str}`.

   **Verdicts:**
   - all pass → `verified`;
   - any failure → **one** retry to the Narrator with the reasons, then re-check;
   - passes after the retry → `rephrased` (`draft_text` and `reason` kept);
   - fails again → `blocked`;
   - judge timeout (`JUDGE_TIMEOUT_S = 6`) → `delayed`.

   Fill `checker` (`reconciled`, `judge_supported`, `retries`, `model`, `latency_ms`). Write claims through the internal MCP server's `put_claims`.
6. **Beat pipeline (`agents/pipeline.py`):** `narrate_and_check(match_id, beat_id, mode) -> list[Claim]`. It fetches the bundle, narrates, checks and writes. Each step gets an OpenTelemetry span with `gen_ai.*` attributes, and the beat's total latency is recorded. Live-stream wiring and the Agent Framework workflow come Friday; keep this a plain async function they can call.
7. **Evals (`evals/`).**
   - `evals/adversarial/claims.yaml`: **30 bad claims** and **10 good claims**, each tied to a real beat in a fixed match (`red_card_flip` seed 3, `end_to_end` seed 1, `late_comeback` seed 4) by beat id. Each has `text`, `fact_ids` and `expected` (`blocked` or `rephrased` for bad, `verified` for good).

     **Bad-claim mix:**

     | Count | Kind | Example |
     | --- | --- | --- |
     | 7 | Wrong number | "8 m" when the fact says 7 |
     | 5 | Number with no cited fact | |
     | 6 | Overclaiming adjective | "dominant" from 54% possession |
     | 4 | Invented cause | "tired legs" |
     | 3 | Wrong player or side | |
     | 2 | Wrong minute | |
     | 3 | Outside knowledge | season form, a real club, "their best start in years" |

     Fictional names only. Mark the file as test data in a header comment; the voice rules don't apply to the bad claims.
   - `evals/run.py`, `make evals JUDGE=<deployment>`, and `make bakeoff`, which runs every candidate. For each candidate it reports:
     - bad claims caught, split into **caught by code** (reconciler or lint) and **caught by judge**;
     - good claims wrongly blocked;
     - judge latency p50 and p90;
     - tokens per claim.

     Write `evals/reports/<date>-<deployment>.json` and one combined `evals/reports/bakeoff.md` table.
   - **Pick rule (in code, not by hand):** among candidates with **at least 28 of 30** caught, **at most 1 of 10** good claims blocked, and **judge p90 at most 4 s**, choose the highest catch count, then the lower p90. If none qualify, choose `gpt-5-mini` with the judge prompt and say so in the report. The winner is written to `models.yaml`.
   - These evals call real models. CI runs only the reconciler, lint and fake-client tests. `make evals` and `make bakeoff` are manual, and also run nightly later.
8. **End-to-end check (manual, reported):** run `narrate_and_check` on every beat of `red_card_flip` seed 3 in `fan` mode with the winning judge. Report claims per verdict and beat latency p50 and p90 (target p90 at most 8 s).
9. **Docs:** append to ADR 0002's Decision log (Oct 22): the Claude Marketplace failure and open support case, the two candidates, the bake-off rule, and the winner with its numbers. Add the bake-off table to `docs/ARCHITECTURE.md` under the Checker.

## Tests (CI, no model calls)

- **Reconciler known answers:**
  - "back line dropped 7 m" against a fact rendering "7 m" passes;
  - "8 m" fails and names "8 m";
  - "64 per cent" matches a fact with rendering "64%" and "64 per cent";
  - a number in a claim with no cited facts fails;
  - citing an unknown fact id fails.
- **Checker state machine with a fake LLM client:**
  - pass → verified;
  - fail then pass → rephrased with `draft_text`;
  - fail twice → blocked;
  - judge timeout → delayed;
  - a claim that fails reconciliation never reaches the judge (assert the fake judge was not called).
- **Narrator prompt builder:** picks examples matching kind and mode, always includes one AMENDED pair, and never includes `ex-00`.
- **Structured-output helper:** retries once on invalid JSON, then raises.
- **Schema:** every claim written validates against `claim.schema.json` with the new id form.
- **Part 0:** the two tests above.

## Verification signal (show the output)

1. `make lint typecheck test` exits 0; CI green.
2. `evals/reports/bakeoff.md`, and which judge won and why.
3. The end-to-end summary from part 8, plus three example claim chains:
   - one `verified`;
   - one `rephrased`, showing draft → reason → final;
   - one `blocked`, with its reason.
4. MCP Inspector against `make api-dev`: connects, lists tools, and `list_beats` works.

## Omissions list (required in the PR)

Model behaviours seen only once; any adversarial claim judged ambiguous; anything the `/openai/v1` route didn't support for the non-OpenAI judges; cost per full match in tokens.

## Out of scope

Live-stream wiring of claims and verdicts, the Agent Framework workflow, Composer and Producer (Friday); the Localizer (Sunday); UI; Bicep changes, except a role assignment if the judges need one (say so if they do).
