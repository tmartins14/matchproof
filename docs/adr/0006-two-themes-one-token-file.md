# ADR 0006: Two themes, Broadcast and Editorial, from one token file

**Status:** accepted, 2026-10-18; amended 2026-10-23

## Context

Broadcast conventions (dark, condensed type, made for overlays on footage) suit the judges and the brief. The author's own editorial brand (cream, Fraunces and Geist, crimson and navy) suits the portfolio. Light and dark mode would duplicate effort without adding meaning.

## Decision

- The viewer switches between **Broadcast** and **Editorial**; these replace light and dark mode. Default follows the system colour scheme.
- Both themes are one token file (colour, type, radius, spacing). Components read tokens only.
- Broadcast tokens are a placeholder until the design pass on Sat Oct 24 (references, Hallmark study, hand-edited DESIGN.md, Impeccable critique). Editorial reuses the existing brand.
- Never imitate a real broadcaster's or the Premier League's graphics package.

> **Oct 23 addendum.** Editorial is deferred to after submission; Broadcast ("Floodlight", `docs/DESIGN.md`) ships alone. Reason: judges score mostly from the video, a theme toggle shows nothing about verification, and two themes double the UI work in the last four days. The single token file and the colour-literal lint stay, so Editorial can return as a second token set without component changes.

## Consequences

- A lint rule or test fails on hard-coded hex colours in components.
- UI PRs show screenshots in both themes.
