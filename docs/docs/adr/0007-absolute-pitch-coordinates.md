# ADR 0007: Absolute 120 × 80 pitch coordinates, home attacks toward x = 120

**Status:** accepted, 2026-10-18

## Context

StatsBomb-style data stores each event in its own team's attacking direction. That suits per-team analysis but makes live rendering of 22 players and both teams' events error-prone: every draw call has to flip half the data.

## Decision

- All events, frames and overlays use absolute coordinates on a 120 × 80 pitch, origin top-left.
- The home team attacks toward x = 120 in both halves. There is no half-time switch in the synthetic data.
- Extractors that need team-relative values (distance to goal, progressive passes) compute them explicitly with a helper, never by re-storing data.

## Consequences

- The renderer draws data as stored.
- Facts that mention distance to goal state which goal, in code.
