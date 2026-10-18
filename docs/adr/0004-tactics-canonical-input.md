# ADR 0004: Tactics are the canonical generator input; the brief is a view of them

**Status:** accepted, 2026-10-18

## Context

Users can set up a match with structured tactics or with a free-text brief, and expect the two to stay in sync. The generator must be deterministic.

## Decision

- `MatchBrief.tactics` (formation; press, directness and line height per team; storyline) plus `seed` fully determine the match.
- Tactics → brief: a deterministic template in code.
- Brief → tactics: the Composer agent returns structured tactics, which the UI shows for the user to confirm. The model step is not deterministic; the confirmed tactics are.
- The last edit wins: changing tactics rewrites the brief; reading a brief updates the tactics but keeps the user's wording.

## Consequences

- Determinism is testable without any model call.
- The Composer's job is narrow and evaluable: given a brief, produce the expected tactics. Add 10 brief → tactics cases to the eval set.
