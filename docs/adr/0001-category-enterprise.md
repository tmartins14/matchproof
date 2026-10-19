# ADR 0001: Declare Best Enterprise Solution

**Status:** accepted, 2026-10-18

## Context

Each entry declares a category and may win one Grand Prize and one Category Prize. Judges can reassign entries. Matchproof's core idea, verified claims with an audit trail, matches the Enterprise description: "reliability, transparency, and controls required for use in production environments". Multi-Agent is likely the most contested category.

## Decision

Declare **Best Enterprise Solution**. Build the agent design to also meet every Multi-Agent test (distinct roles, shared state, handoffs, failure recovery) so a reassignment does not hurt.

## Consequences

- Enterprise evidence becomes first-class scope: eval report, trace links, cost and rate limits, degradation paths, data statement.
- The pitch and video lead with trust on air, not with the agent count.

## Update, 2026-10-19: positioning after reviewing the field

A review of the 303 projects on the Innovation Studio page (titles and short descriptions) found about 51 pitching verified or evidence-backed narration, several with near-identical taglines. Verification is now table stakes for this brief, not a differentiator. The category choice stands, because the Enterprise description still rewards it, but the pitch changes:

- **Lead with the controllable match.** Tactics in, a different match out, deterministically. Fewer than 5 entries mention tracking, positions or simulation.
- **Frame the tactics panel as a scenario harness**, not a fan toy: you cannot certify an AI narration system you cannot feed controlled inputs. Same tactics and seed, same match, known ground truth for every claim.
- **Positional claims checked against freeze frames** are the hero moment (line height, compactness, distance between lines).
- **Drop "receipts" from product copy and the pitch.** The rail is the evidence rail; verdicts use football's review language (see `docs/VOICE.md`).
