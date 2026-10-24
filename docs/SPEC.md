# Matchproof — Product Spec

**One line:** Set the tactics, watch the match, and see every claim checked against the evidence before it airs.

## Problem

AI can already write match commentary, recaps and "why it mattered" explanations. A studio cannot put them on air, because nobody can prove they are true. One invented statistic in a live broadcast is a correction, a credibility hit, and a reason to switch the tool off. The gap is not generation. It is verification at live speed.

## Users

| User | Needs | Mode |
| --- | --- | --- |
| Casual fan | A clear story of the match in their language, no jargon | Fan |
| Analyst | The numbers behind each moment, and where they came from | Analyst |
| Studio producer | Confidence before anything airs; what was changed or blocked, and why | Producer |
| Graphics operator | Timed, machine-readable overlays to key over the feed | Overlay route |
| AI product owner | Proof the narration system is safe to deploy: controlled scenarios with known ground truth, and a measured catch rate | Tactics panel as a scenario harness; eval report |

## What it does

1. Takes a tactical setup (formation and three dials per team, plus a storyline or custom planted moments such as a red card at 30′) or a free-text brief, kept in sync both ways. Custom moments make the tactics panel a scenario harness: set up a situation, then watch every claim about it get checked.
2. Generates a full synthetic match: events plus positions for all 22 players, calibrated against real-match distributions.
3. Streams it live at 1×, 3× or 6× speed, or plays a cached run.
4. Detects key moments, narrates them from computed facts, and checks every claim before it is shown.
5. Shows the pitch with live players, freeze frames and overlays; a narrative feed; and an evidence rail tracing claim → fact → events → verdict. While a claim is checking, the pitch highlights the players or zone it is about.
6. Personalises by mode (fan, analyst, producer), language (EN, ES, more if time), club and player focus.

## Success criteria (measured, not asserted)

| Criterion | Target | Measured by |
| --- | --- | --- |
| Grounding | 100% of published claims cite at least one fact; 100% of numbers reconcile | Eval runner on 3 golden matches |
| Checker recall | ≥ 28 of 30 adversarial claims caught | Adversarial eval set |
| Latency | ≤ 8 s from beat detection to verdict, p90 | Eval run timings |
| Realism | Every calibration metric inside its real-match band on 4 seeds | Calibration tests |
| Determinism | Same tactics + seed → byte-identical event log | Unit test |
| Translation integrity | Every number and name survives EN → ES unchanged | Invariance test |
| Availability | Demo URL up through Nov 10 with no login | Uptime check |

## Non-goals

- Real Premier League data, footage, clubs, players or marks.
- Computer vision or auto-eventing from video.
- Tracking-data-grade player movement. Movement must look plausible to a broadcast viewer, not pass an analyst's audit.
- User accounts, persistence of user matches beyond the session, payments.
- Mobile apps. The web app must work at phone width; that is all.

## Hackathon fit

| Judging criterion (20% each) | Where Matchproof scores |
| --- | --- |
| Technological Implementation | Calibrated generator with 22-player positions; schema-first contracts; tests and CI; IaC; managed identity |
| Agentic Design & Innovation | Five agents with distinct roles over one shared match store via MCP; Checker → Narrator retry; live verification |
| Real-World Impact | Overlay JSON a graphics operator can key; claims a producer can trust on air |
| UX & Presentation | Live desk with evidence rail and on-screen review states, three modes, two languages; product text follows `docs/VOICE.md` |
| Category Adherence (Best Enterprise Solution) | Transparency, controls, audit trail, graceful degradation, cost guards |
