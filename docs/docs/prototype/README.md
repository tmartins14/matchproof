# UI prototype

`Main.dc.html` is the clickable prototype the web app is built from. It is a Design Component file: HTML markup with `{{holes}}` and a logic class at the bottom. It does not run standalone; read it as a specification.

## What to take from it

- **Layout and behaviour:** header with scorebug and toggles; brief box with Randomize and Read brief; Tactics panel (formation, three dials per team, storyline); five-stage pipeline strip; pitch with 22 players, ball, freeze frames and overlays; stats, event ticker, momentum strip with clickable moment pins; key-moment feed with verdict stamps; receipts rail; Producer agent log; Calibration view.
- **Theme tokens:** the `tokens()` method holds both themes, Broadcast and Editorial. `apps/web/src/theme/tokens.ts` starts as a copy.
- **Copy:** English and Spanish strings in the `t` objects.
- **State machine:** pre-match → live (1×, 3×, 6×) → full time; cached replay; a 6-second freeze frame when a moment is detected; pinning a moment until Follow live.
- **Tactics ↔ brief sync:** see `teamLine`, `readBriefText` and `setTac`. The real build replaces the keyword reader with the Composer agent.

## What is fake

- Every brief plays the same hand-written sample match: five moments, fixed events and claims.
- The ticker, stats and momentum are simulated from the clock.
- Player positions use the version 1 shape model. The real version 2 movement replaces it (ADR 0005).
- Checker latency is a fixed 2.6 s delay.
- Calibration numbers are placeholders.
- Broadcast theme colours and type are placeholders until the design pass on Sat Oct 24.
