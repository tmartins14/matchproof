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
