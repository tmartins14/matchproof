# UI prototype

Two files, one prototype:

- `prototype.html` runs on its own. Open it in a browser to see and click through the behaviour.
- `Main.dc.html` is the readable source: HTML markup with `{{holes}}` and a logic class at the bottom. It does not run standalone; read it as the specification for logic, copy and theme tokens.

## What to take from it

- **Layout and behaviour:** header with scorebug and toggles; brief box with Randomize and Read brief; Tactics panel (formation, three dials per team, storyline); five-stage pipeline strip; pitch with 22 players, ball, freeze frames and overlays; stats, event ticker, momentum strip with clickable moment pins; key-moment feed with verdict stamps; evidence rail (called the receipts rail in the prototype); Producer agent log; Calibration view.
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
- The prototype still has an Editorial toggle; the build ships Broadcast only.

## Changed since the prototype (Oct 19)

- Oct 23 design pass: Broadcast is now Floodlight (`docs/DESIGN.md`); the match setup collapses to one bar and expands on Edit; Editorial deferred.
- `prototype.html` predates the design pass. `Main.dc.html` and `reference/` are authoritative.
- **Verdict labels:** the build uses CHECKING, STANDS, AMENDED, OVERTURNED and HELD (`docs/VOICE.md`), not Verified, Rephrased and Blocked. AMENDED shows the old wording struck through above the new.
- **Checking state:** the pitch highlights the players or zone the claim is about. No spinner.
- **No AI-coded UI:** no sparkle icons, gradients, glow, typing animation or chat bubbles; the words "AI" and "agent" stay out of the live desk (the Producer agent log stays in the dev panel).
