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
