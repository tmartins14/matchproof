# ADR 0002: Microsoft Foundry models, Microsoft Agent Framework orchestration, Python throughout

**Status:** accepted, 2026-10-18

## Context

Stage One judging checks that entries "reasonably apply the required technologies". Foundry and Agent Framework are named hero technologies. The existing football-analytics work is Python, and the seam rule puts all computation in Python.

## Decision

- Agents run on models deployed in a Microsoft Foundry project, called with managed identity.
- Orchestration uses the Microsoft Agent Framework Python SDK: a sequential workflow with one bounded Checker → Narrator retry per beat.
- The model deployment name lives in config. Pick the model on Sunday Oct 18 after checking regional availability and quota; prefer a Claude model in Foundry if available, otherwise the strongest available GPT deployment.
- Fallback if Agent Framework costs more than 2 hours to get working: the Foundry Agent Service SDK with the same roles and the same workflow shape.

## Consequences

- All agent calls go through one thin client module so the model and SDK can change without touching agent logic.
- Every prompt is a versioned file; a change re-runs the evals.

## Decision log

### 2026-10-18: model and region for the walking skeleton

- **Region:** `eastus2`. The Foundry model catalog for this subscription lists Claude there, and in `swedencentral`, `eastus` and `westus3`. `canadacentral` and `canadaeast` list OpenAI models only.
- **Claude is blocked on quota.** The first `azd up` failed with `InsufficientQuota`: the limit for "Tokens Per Minute (thousands) - Claude Sonnet 5.5" is 0 in `eastus2`. A read of `az cognitiveservices usage list` for `eastus2`, `eastus`, `swedencentral`, `westus3`, `canadaeast` and `canadacentral` shows a limit of 0 for every Claude model and for every GPT chat model except `gpt-5-mini`.
- **Model used for now:** `gpt-5-mini`, version `2025-08-07`, `GlobalStandard`, deployment name `gpt-5-mini`. It is the only chat model with quota on this subscription (limit 500 thousand tokens per minute in `eastus2`, `eastus`, `swedencentral`, `westus3` and `canadaeast`). Requested capacity is 50. This is not the "strongest available" model in the abstract; it is the only deployable one.
- **To switch back to Claude:** request quota for Sonnet 5.5 (catalog default version `2`, `GlobalStandard`) in the Azure portal, then change `llm_client.py` to the Anthropic Foundry client, set `modelProviderData` in `infra/modules/foundry.bicep` (it needs the real organization name, country and industry, and accepts Anthropic's Marketplace terms), and swap the role to Cognitive Services User. Callers do not change.

### 2026-10-19: Claude quota approved; the Checker's judge moves to Claude

- **Quota:** the subscription now shows 80K TPM for Claude Sonnet 4.5, 4.6, 5 and 5.5 (Global Standard, plus US Data Zone Standard for 5 and 5.5). The portal labels it shared quota, so treat it as one 80K pool across the Sonnet family and deploy one model.
- **Decision:** the Checker's LLM judge uses **Claude Sonnet 5.5**, deployment name `checker-judge`, capacity 50 (thousands of TPM) to leave headroom in the shared pool. Prefer **US Data Zone Standard** so verification stays on Azure in the US, which is the stronger enterprise story; fall back to Global Standard if Data Zone cannot be deployed into the `eastus2` Foundry resource.
- **The Narrator, Composer, Producer and Localizer stay on `gpt-5-mini`.** Writer and judge are different models from different vendors, so the judge is not grading its own output.
- **Not yet verified:** a smoke-test deployment and call. The Bicep and client changes listed under "To switch back to Claude" land with the Checker prompt (Thu Oct 22): the client module gains a second provider; agent code does not change.
- **Cost:** Azure credits do not cover Claude; usage bills to the card. The budget alert in `infra/modules/budget.bicep` must be checked before evals run in a loop.

### 2026-10-22: the Claude judge is blocked; the bake-off picks gpt-5-mini

- **Claude Marketplace deployment failed twice** with `MarketplaceSubscriptionCannotBeCompleted`. A support request is open. Until it resolves there is no Claude judge.
- **Candidates deployed in `ais-oou4h3al`:** `judge-mai` (Microsoft MAI-Thinking-1) and `judge-grok` (xAI grok-4.7). Both answer through the shared `/openai/v1` endpoint with the same Entra token. `judge-mai` rejects every `response_format`, so the schema goes in the prompt; `judge-grok` takes `json_schema`.
- **Rule (in `evals/pick.py`):** among candidates with at least 28 of 30 bad claims caught, at most 1 of 10 good claims blocked and judge p90 at most 4 s, take the most caught, then the lower p90. If none qualify, use `gpt-5-mini` with the judge prompt.
- **Result:** `judge-mai` caught 25/30, blocked 0/10 good, p90 25.0 s, and gave no answer on 12 of 27 judged claims. `judge-grok` answered none of its 27 (HTTP 429 `pd_decode_pushback`, "All available decode workers reached a configured load limit", and timeouts), so it caught only the 13 that code stops. Neither qualified.
- **Winner: `gpt-5-mini` (fallback judge, own prompt `judge.v1.md`):** caught 29/30 (13 by code, 16 by the judge), blocked 0/10 good, p50 1.7 s, p90 2.1 s, 658 tokens per judged claim. The one miss is a wrong "since half-time" on a back-line change that is measured from the red card. `models.yaml` now has it as the active judge.
- **Not independent:** the Narrator and the judge are now the same model, which the 2026-10-19 entry avoided. The judge has a different prompt and sees only the claim and its cited facts, but it is not a different vendor. Revisit when the Claude deployment works, and re-run `make bakeoff` then (and for `judge-grok` once its capacity recovers).

### 2026-10-22 (evening): judge v2 and a second bake-off

- **Why:** on the end-to-end run the v1 judge amended action verbs ("smashes", "lashes", "Rivermouth press", "sit higher") and passed motive and team-state clauses ("as they push for a response", "pinned back", "left short upfront").
- **Change:** `judge.v2.md` states the rubric. Verbs that describe the action are allowed when the event and outcome match the facts. Team state, motive, cause, comparison and anything about an uncovered period need a fact. A `motive` problem category is added. 12 claims were added to the eval set (8 bad with a motive or state clause, 4 good with vivid verbs): 38 bad and 14 good. The pick rule scales to at least 35 of 38 caught, at most 1 of 14 good blocked, p90 at most 4 s.
- **Result (v2, all three on the 52-claim set):**

| Judge | Bad caught (of 38) | by code | by judge | Good blocked (of 14) | Unavailable | p50 | p90 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| judge-mai | 32 | 14 | 18 | 0 | 11 | 19.3 s | 25.3 s |
| judge-grok | 38 | 14 | 24 | 0 | 1 | 7.8 s | 22.6 s |
| gpt-5-mini (fallback) | 37 | 14 | 23 | 0 | 0 | 1.3 s | 1.7 s |

- **Decision: `gpt-5-mini` stays the judge.** `judge-grok` was accurate this time (38 of 38, no 429s) but far too slow for a per-claim check, p50 7.8 s against a 4 s p90 limit; `judge-mai` is slow and unavailable on 11 claims. The only claim `gpt-5-mini` missed is "since half-time" on a change measured from the red card.
- **Still the same model as the Narrator.** The judge passes some adjectives that no fact measures ("brilliant", "tidy") and a few flourishes ("shielding their goal"); motive and state clauses are now caught. Revisit when the Claude deployment works.


### 2026-10-22 (night): the workflow runs on Agent Framework; its MCP tool support does not

- **Workflow: used.** `agent-framework-core` 1.23.0, `WorkflowBuilder`: Producer, Narrator and Checker are executors, with one conditional edge from Checker back to Narrator. It worked in about 20 minutes, including the retry loop. Messages between executors are copied by the framework, so they carry plain data only; the beat's span context and the Producer's turn gate are kept beside the run and looked up by key.
- **MCP tool support: abandoned inside the timebox.** The framework's `MCPTool` needs the `mcp` package at 2.2 or later (it reads `ClientSession.protocol_version`, which 1.x lacks), and `packages/mcp_match` and the public `/mcp` mount are built on `mcp` 1.x (`FastMCP`, `session_manager`), which 2.x renamed and reorganised. Moving both was out of scope for this task. The agents instead reach the internal server through a plain in-process `ClientSession` over a memory transport (`api.agents_runtime.SessionServer`), with the same four tools. Revisit when the server moves to `mcp` 2: the workflow does not change, only the adapter.
- **Fallback not needed.** The Foundry Agent Service SDK and a hand-written orchestrator were not used.
- **Inline judge and auditor.** The inline judge stays `gpt-5-mini` for latency (p50 1.3 s, p90 1.7 s on the 52-claim set, 37 of 38 bad caught). The independent auditor is `judge-grok`, a second vendor, run log-only after the Checker settles a claim: it caught 38 of 38 bad claims with none of 14 good blocked, but its p50 of 7.8 s and p90 of 22.6 s are too slow to sit in front of a verdict. It never changes a published verdict in this version; a disagreement goes to the Producer log, the trace and `GET /matches/{id}/audit`.

### 2026-10-23 (afternoon): judge v3 and corrections by consensus

On the live run the independent auditor disagreed with the inline judge on 3 of 9 claims (and on 3 more that morning), and was right each time: an evaluative adjective ("smart"), a cause clause ("leaving more space"), and a fact relabelled or compared with no before fact ("share of play has risen"). Banning words one at a time does not scale, so the loop is closed two ways.

- **Eval set: 44 bad and 18 good.** The six disagreements are now `adv-39` to `adv-44`, rebuilt on the real beats with the facts they cited, plus four near-miss good claims (`good-15` to `good-18`). Pick rule: at least 41 of 44 caught, at most 1 of 18 good blocked, judge p90 at most 4 s. Four of the six are now caught by code (`smart`, `composed`, `edge in front` and the `risen` family are on the word lists); `adv-40` to `adv-42` still reach the judge.
- **Judge v3** (`judge.v3.md`): v2's rubric plus a "commonly missed" section with one line per failure type: an evaluative adjective, a consequence or cause clause, a fact called by another name (opposition-half share called "share of play"), a change word with no before or change fact for that measure (a score or lead fact supports only the lead and the score), and a "since" point that is not the fact's. The auditor keeps `judge.v2.md` so the two stay independent.
- **Bake-off** (`evals/reports/bakeoff.md`, `judge-mai` skipped): `gpt-5-mini` caught 42 of 44, blocked 0 of 18 good, p50 1.5 s, p90 2.1 s. A first v3 run caught 43 of 44, and v2 on the same set caught 40 of 44 with 1 of 18 good blocked. `judge-grok` also caught 42 but was unavailable (timeout) on 2 claims, p50 8.8 s, p90 22.5 s. `gpt-5-mini` stays the judge, now on v3. Still missed, in at least one run: `adv-41` ("share of play has risen to 53%", with a lead fact cited) and `adv-42` ("a tighter 730 square metres shape", with a back-line change cited). Both lean on a fact label that says "smaller is tighter" or a lead fact that is cited for another reason; the judge is inconsistent on them, so the rule was not loosened.
- **Corrections by consensus** (`agents/consensus.py`). When the auditor disagrees on a `verified` or `rephrased` claim, the inline judge re-checks it with the auditor's problem and reason in front of it. Only if it now agrees does the claim change: the Narrator rewrites it once with both reasons, and the full check (reconcile, lint, judge) decides `rephrased` with the new text or `blocked`. If the re-check still supports the claim, nothing changes on screen and the disagreement is logged as unresolved. One correction per claim, inside the token cap, and stopped when auditing stops. A correction is sent as a `verdict` with a `correction` object that always holds the previous text.
- **Why not let the auditor decide alone.** It was right 6 of 6 here, but it is one model; a claim already on air changes only when two models agree it is wrong, and the viewer is shown the change.

