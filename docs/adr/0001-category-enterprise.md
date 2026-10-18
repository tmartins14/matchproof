# ADR 0001: Declare Best Enterprise Solution

**Status:** accepted, 2026-10-18

## Context

Each entry declares a category and may win one Grand Prize and one Category Prize. Judges can reassign entries. Matchproof's core idea, verified claims with an audit trail, matches the Enterprise description: "reliability, transparency, and controls required for use in production environments". Multi-Agent is likely the most contested category.

## Decision

Declare **Best Enterprise Solution**. Build the agent design to also meet every Multi-Agent test (distinct roles, shared state, handoffs, failure recovery) so a reassignment does not hurt.

## Consequences

- Enterprise evidence becomes first-class scope: eval report, trace links, cost and rate limits, degradation paths, data statement.
- The pitch and video lead with trust on air, not with the agent count.
