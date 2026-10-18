# ADR 0005: Fix the position contract first, upgrade movement quality later

**Status:** accepted, 2026-10-18

## Context

The desk shows all 22 players. Movement must look plausible to broadcast judges; it does not need to match real tracking data. Realistic movement costs 4 to 6 hours, and the weekday build slots are 3 hours.

## Decision

- `PositionFrame` at 5 Hz plus one freeze frame per event is the fixed contract.
- Version 1 (Tue Oct 20): a formation shape model that shifts with the ball and the line-height dial.
- Version 2 (Mon Oct 26, committed, never cut): role-based movement with speed and acceleration caps, and the passer, receiver and shooter pinned to each event location.
- If the licences allow, calibrate distance covered and sprint counts against open tracking samples, and show the result on the calibration page.

## Consequences

- The renderer, extractors and Checker are built once against version 1 and need no change for version 2.
- A test asserts that every event's actor is within 1 m of the event location in its freeze frame.
