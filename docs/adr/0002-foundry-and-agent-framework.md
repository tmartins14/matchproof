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
- **Model:** `claude-sonnet-5-5`, version `2` (the catalog default, generally available, `GlobalStandard`), deployed as `claude-sonnet`. Claude is preferred by this ADR; Sonnet over Haiku because the ADR asks for the strongest available model, and the deployment name and model are Bicep parameters.
- **Fallback:** `gpt-5.5` (`GlobalStandard`) is listed in `canadacentral` and `canadaeast` if Claude cannot be deployed to this subscription.
- **Quota:** the catalog shows a default capacity of 10 (thousand tokens per minute). Per-subscription quota was not readable before deployment (`az cognitiveservices usage list` returned nothing while `Microsoft.CognitiveServices` was unregistered). Requested capacity is 10. Actual quota seen at deploy time is recorded below.
- **Eligibility:** deploying a Claude model sends an attestation (`modelProviderData`: organization name, country, industry) that accepts Anthropic's Marketplace terms on the deployer's behalf. The Bicep has no defaults for these.
