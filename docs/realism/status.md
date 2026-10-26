# Realism status (prompt 18, Part B only)

Part C is out of scope for this run: no `feat/realistic-play`, no `engine.py` / `shape.py` changes.

| gate | time (ET) | result |
| --- | --- | --- |
| B1 measure | 14:45 | pass: `sim/realism.py`, `docs/realism/baseline.json` |
| B2 fix (`positions.py` only) | 15:55 | done; numbers below |
| B3.1 same events | 15:55 | pass: SHA-256 of the events stream identical for the 6 pack fixtures and calibration seeds 1-8 x 4 storylines (38 matches) |
| B3.2 same beats | 15:58 | pass: beat ids identical for fx-01 to fx-06 |
| B3.3 realism | 15:55 | pass: offside 0.60% of forward passes (limit 1%), speed 9.43 m/s (9.5), acceleration 5.73 m/s² (6.0), teammate overlap 0.526% (was 0.646%) |
| B3.4 calibration | 16:00 | pass: `pytest -m slow -k calibration` and `sim calibrate --seeds 1-8` (every row, shape rows included) |
| B3.5 fixtures | 16:04 | regenerated: `stream-short`, `metric-families`, six `public/trials/streams`; `desk.json` and `setup.json` unchanged; adv-42's quoted compactness 730 -> 755 |
| B3.6 checks | 16:17 | pass: lint, typecheck, check-contracts, `pytest -n 2 -m "not slow"` (646 passed, 1 xfailed), `npm test` (80 passed) |

## Realism, before and after (6 pack fixtures + calibration seeds 1-8 x 4 storylines)

| measure | before | after |
| --- | --- | --- |
| forward passes judged | 7878 | 7878 |
| offside at the pass (share of forward passes) | 9.39% | 0.60% |
| max speed, m/s (cap 9.5) | 7.91 | 9.43 |
| max acceleration, m/s² (cap 6.0) | 24.82 | 5.73 |
| teammate overlap (share of frames) | 0.646% | 0.526% |
| back-line spread, m (lower is tighter) | 1.48 | 1.78 |
| pinned-actor placements over one step's run | 1050 | 3690 |

Values (all in `positions.py`): speed cap 9.5 m/s reported (8.8 m/s inside, for 0.1 m rounding), acceleration 5.0 m/s²
(measured over 0.6 s windows, at most 5.73), offside margin 0.8 m, teammate separation nudge under 3.5 m.

Assumptions and costs:
- Speed and acceleration are measured on running. An event actor is still placed on its event location (ADR 0005), which is a placement, not a step; those are counted separately (`snap_jumps`). They rose from 1050 to 3690 over 24.1 M player steps (0.004% to 0.015%, the existing test allows 0.1%) because capped acceleration reaches fewer of the engine's event locations in time. Removing them needs the engine to place events where a player can be, which is Part C.
- Back-line spread rose from 1.48 m to 1.78 m. Not a B gate (it is C's), reported for the record.
