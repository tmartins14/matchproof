# DESIGN.md — Matchproof live desk

The visual system for the live desk. `apps/web/src/theme/tokens.ts` holds the values; this file says what they mean and how components use them. The reference implementation is `docs/prototype/Main.dc.html`: the Broadcast branch of `tokens()` and the markup. The screenshots in `docs/prototype/reference/` are the visual target. If this file and the prototype disagree, this file wins; flag it in the PR.

## Identity: "Floodlight"

A studio desk on a blue set:

- a saturated ocean-blue field;
- white chips with hard offset shadows;
- slanted cuts and condensed caps;
- the pitch as the only green on screen, framed like a video feed.

**Lime means verified.** It marks STANDS, LIVE and the active pipeline stage, and nothing else.

One theme ships. The Editorial theme from ADR 0006 is deferred until after submission. Every visual value stays a token in one file, so a second theme can return later as a second token set with no component rewrites.

## Principles

1. **Legible in a 1:50 video at 720p.** Judges mostly score from the video. Big blocks, high contrast, condensed caps, tabular numbers. Thin grey text loses.
2. **One signature: the verdict.** The stamp and the evidence rail are the product. Nothing else competes with lime.
3. **Motion lives in the geometry, not in animation.** Slanted cuts and the chevron carry the energy. Animation is reserved for state: the LIVE dot and the CHECKING pulse.
4. **On-air depth.** White chips on colour, with hard offset shadows and no blur. That is the broadcast look, not glass or glow.
5. **Nothing looks generated.** No sparkle icons, gradients, glow, typing animation, chat bubbles or spinners (`docs/VOICE.md`). The words AI, agent, model and generated never appear in the live desk.
6. **Own identity.** Never imitate a real broadcaster's or the Premier League's graphics package: no royal blue with red slashes, no purple with cyan, no italic chip stacks, no real marks.

## Colour

| Token | Value | Role |
| --- | --- | --- |
| `bg` | `#0B4F8A` | The field (ocean blue) |
| `surface` | `#073A69` | Panels, setup bar, pipeline stages, minute blocks |
| `raised` | `#0E5D9F` | Selected claim, chevron band |
| `input`, `code`, `shadow` | `#042848` | Inputs, fact code blocks, every offset shadow |
| `line` / `line2` / `strong` | `#3C7CB5` / `#1B5C94` / `#6A9CC9` | Rules, card borders, outline buttons |
| `text` / `text2` / `muted` | `#FFFFFF` / `#E6F0FA` / `#D3E5F7` | Text on blue |
| `chip` / `ink` | `#FFFFFF` / `#0A2540` | White chips and the navy text on them |
| `lime` (`verified`, `live`, `primary`, `stageOn`, `focus`, `ball`) | `#D7F35B` | STANDS, LIVE, Kick off, active stage, focus ring, ball |
| `limeInk` | `#14200F` | Text on lime |
| `amended` / `amendedInk` | `#FF9A3C` / `#2E1A00` | AMENDED |
| `overturned` / `overturnedInk` | `#FF5A4E` / `#2E0A06` | OVERTURNED. Red appears nowhere else |
| `checking` / `checkingBorder` | `#FFFFFF` / `#D3E5F7` | CHECKING and HELD outlines |
| `home` / `homeText` | `#FFFFFF` | Rivermouth |
| `away` / `awayText` | `#7CC4FF` / `#A8D8FF` | Ashford Vale |
| `pitch` / `pitchFrame` | `#0F5A38` / `#FFFFFF` | Flat pitch, white frame |
| `pitchLine` | `#FFFFFF` at 0.55 | Pitch markings |
| `zone` | `rgba(215,243,91,0.16)` | Evidence highlight on the pitch while CHECKING |
| `bandA` / `bandB` / `bandC` | `#0E5D9F` / `#D7F35B` / `#09457A` | Backdrop chevron, lime sweep, bottom band |

The team colours differ in lightness as well as hue, so they read in greyscale and for colour-blind viewers.

### Contrast (measured, WCAG 2.x)

| Pair | Ratio |
| --- | --- |
| `text` on `bg` | 8.4:1 |
| `text` on `surface` | 11.5:1 |
| `muted` on `bg` | 6.5:1 |
| `muted` on `raised` | 5.3:1 |
| `ink` on `chip` | 15.5:1 |
| `limeInk` on lime | 13.6:1 |
| `amendedInk` on `amended` | 7.9:1 |
| `overturnedInk` on `overturned` | 5.9:1 |
| `awayText` on `surface` | 7.7:1 |
| Away player dot on pitch (non-text) | 4.4:1 |

Any new pair must reach 4.5:1 for text and 3:1 for UI and graphics. Put the ratio in the PR.

## Type

| Role | Face | Use |
| --- | --- | --- |
| Display | Archivo Narrow 600–700 | Headings, chips, stamps, lower thirds, scores. Uppercase for headings, chips and lower-third headlines |
| Body | Archivo 400 / 500 / 600 | Claims, prose, labels |
| Mono | Geist Mono 400 / 500 | Clock, IDs (F-, E-, C-), timestamps |

- All numbers use `font-variant-numeric: tabular-nums`.
- Load fonts with `next/font/google` only.
- Body text never goes uppercase.

Scale (px):

| Size | Use |
| --- | --- |
| 13 | Labels |
| 15 | Body |
| 17–18 | Small display |
| 20–22 | Lower-third headline |
| 24 | Section tab |
| 34 | Pitch title |
| 72 | Hero score |

The minimum is 12px, and only for mono.

## Shape and depth

| Token | Value | Used by |
| --- | --- | --- |
| `radius` | `0` | Everything. No rounded corners except the player dots and the LIVE dot |
| `cut` | `polygon(8px 0, 100% 0, calc(100% - 8px) 100%, 0 100%)` | Middle segmented chips, setup-bar buttons, stamps, pipeline stages, lower-third caption, moment pins |
| `cutStart` | `polygon(0 0, 100% 0, calc(100% - 8px) 100%, 0 100%)` | First chip of a group: straight left side, slanted right |
| `cutEnd` | `polygon(8px 0, 100% 0, 100% 100%, 0 100%)` | Last chip of a group: slanted left side, straight right |
| `cutTab` | `polygon(0 0, 100% 0, calc(100% - 12px) 100%, 0 100%)` | Section tabs, minute blocks, wordmark |
| `shadowPanel` | `8px 8px 0` + `shadow` | Panels, pitch |
| `shadowChip` | `5px 5px 0` + `shadow` | Scorebug, wordmark, key-moment bars, caption |
| `pitchFrameWidth` | `4px` | Pitch frame |

Shadows never have blur. The cut always slants the same way (top-left to bottom-right), so the screen reads as moving right, toward the attacking end.

**Rules for any element with a cut.**

- Its shadow comes from `filter: drop-shadow(...)` on an unclipped wrapper (`.mp-lift`), never `box-shadow` on the element, which `clip-path` clips.
- It has no border. A square container with a border is fine.
- At the edge of a square container it uses `cutStart` or `cutEnd`, so its outer side is straight and meets the border without a wedge-shaped gap.
- The backdrop's lime sweep may pass between controls, but never behind text or a control's own surface.

**Focus on cut elements.** `clip-path` clips an outside outline. Every element with a cut uses an inset focus ring: `outline: 2px solid lime; outline-offset: -3px`.

## Components

- **Backdrop.** A chevron band (`bandA`) and a thin lime sweep (`bandB`) down the right edge, plus an angled `bandC` band across the bottom. `pointer-events: none`, behind all content. It may crop on phones.
- **Wordmark.** A white "MATCHPROOF" chip and a lime "LIVE DESK" chip overlapping by 6px, `cutTab`, `shadowChip`.
- **Scorebug.**
  - Team chips: `home` and `away` backgrounds with `ink` text.
  - Score on `surface`.
  - Clock in mono.
  - LIVE chip on lime with a pulsing dot.
  - `shadowChip`.
- **Segmented control** (mode, language, speed). Active: `chip` / `ink`. Inactive: transparent with `muted` text. The group keeps a square box and border with 3px padding. Each chip's cut comes from its position: the first is `cutStart`, the last `cutEnd`, the rest `cut` (a group of two is `cutStart` then `cutEnd`), so the selected chip sits 3px from the border on every side. Minimum height 40px, or 44px for primary actions.
- **Match setup bar.**
  - One row, always visible:
    - a `cutTab` label;
    - a `cutTab` label;
    - the summary: 15px `text2`, line-height 1.45, max width 760px. It shows all of it and wraps in its own column, never under the tab or the buttons. The two teams' shape sit on the first line and the storyline on the second. It updates live while the editor is open. A brief the user wrote shows "Custom brief" in `muted`, then the brief's first sentence in full;
    - Edit tactics and brief (`aria-expanded`; the chevron rotates), Randomize, Kick off, Watch cached replay, top-aligned and level with the tab. At 390px the tab, summary and buttons stack.
  - Buttons: every one is `cut`, with its depth from a `.mp-lift` wrapper. Secondary buttons are `raised` blocks with `text` (6.8:1) and no border; hover keeps the fill and adds a 2px inset `text` outline (`outline-offset: -4px`); disabled is 45% opacity. Kick off live is `lime` with `limeInk` and an 8px dot before its label. Never put white text on `strong`: it measures 2.9:1.
  - While live, the row holds speed and New match instead, and Edit is disabled.
  - Expanding reveals the brief textarea, Read brief and the tactics fieldset, under a `line` rule. Kick off collapses it.
- **Pipeline strip.** Five stages (name / value / detail) as slanted `surface` blocks with a 4px gap. The active stage has a 3px lime top rule.
- **Section tab.** `h1` / `h2` as a white `cutTab` chip with `ink` caps text. The ticker and momentum labels use a smaller version.
- **Pitch.**
  - Flat `pitch` with `pitchLine` markings, a `pitchFrameWidth` white frame and `shadowPanel`.
  - Players are 11px dots in team colours; the goalkeeper is a square. Players drop to 45% opacity on a freeze frame.
  - The ball is lime.
  - The CHECKING highlight fills the zone or the players with `zone`.
- **Lower-third caption** (on the pitch). Bottom centre, `cut`, `shadowChip`, 18px caps display. Lime while live; white with `ink` text on a freeze frame.
- **Key moment** (feed row).
  - A white bar with `ink` text, a dark `surface` minute block (`cutTab`), the headline in caps, and the verdict stamp at the right edge. `shadowChip`.
  - While any claim in it is CHECKING, the bar drops the white for a dashed `checkingBorder` outline.
  - Expanded, its claims show below on `surface`.
- **Verdict stamp.** The signature element: a filled slanted block (`cut`) in 15px caps display.

  | State | Fill / ink | Notes |
  | --- | --- | --- |
  | CHECKING | Transparent, dashed `checkingBorder`, `checking` text | Pulses; the pitch shows `zone` |
  | STANDS | lime / `limeInk` | |
  | AMENDED | `amended` / `amendedInk` | Old wording struck through above the new; reason on hover and focus |
  | OVERTURNED | `overturned` / `overturnedInk` | Claim text struck through in `muted`; reason shown |
  | HELD | Transparent, solid 1.5px `checkingBorder`, `checking` text | No pulse; "evidence not in yet" |

- **Evidence rail.**
  - `surface` panel with `shadowPanel` and a section tab.
  - At the top, the **stat card**: the fact's number large in a lime `cutTab` block, joined to a white label chip (metric · team, fact ID · window). This is the first frame of the video.
  - Then four steps: Claim, Computed fact (the fact's plain-English `label` = rendered value, with the machine name beneath in 12px mono `muted`), Source events (event rows show ID / event, player / time; window and aggregate rows show what they cover with the clock, and their id in `title`), Verdict.
- **Stats and momentum.**
  - `surface` panels. Home bar in `home`, away bar in `away`, with a 3px gap.
  - The stats panel is headed "Match · to 70′" and shows the latest match-to-date facts at the clock: possession, shots, shots on target, xG.
  - Momentum is one thin bar per closed 5-minute bucket (18 slots, 3px gaps) diverging from a `line` axis: positive values rise in `home`, negative drop in `away`, zero is a 2px tick. Height is the fact's value over the largest absolute value so far, scaled to half the strip. Ticks 0′, 45′, 90′ sit below. Moment pins are 24px-wide buttons across the strip: a 2px vertical tick in `chip` at 50% opacity through the full strip height, with the minute label in a row below the axis ticks. The selected pin's tick is solid `lime` and its label always shows; other labels hide when they would overlap a neighbour (the full text stays in `aria-label`). The strip is 72px tall at 1440 and 56px at 390.

## Motion

- The LIVE dot and CHECKING stamps pulse (1.1s opacity).
- The setup chevron rotates and players move (200ms linear).
- Nothing else animates.
- `prefers-reduced-motion: reduce` stops the pulse and the transitions.
- Never: typing or streaming text, skeleton shimmer, spinners, parallax on the backdrop.

## Layout

- Fluid. `main` is a wrapping flex row:
  - match column `flex: 999 1 560px`;
  - feed `flex: 1 1 320px`;
  - evidence rail `flex: 1 1 320px`.

  They stack on a phone.
- The header and toolbars wrap. Touch targets are at least 44px.
- Every content block is `position: relative`, above the backdrop.
- The desk works at 390px wide. The backdrop may crop; content may not.

## Checklist for any UI PR

- Screenshots at 1440 and 390 wide, beside the matching reference.
- No colour literals in components (lint).
- Contrast for any new pair.
- Keyboard: every control is reachable, and the inset focus ring is visible on cut elements.
- No banned visuals or words from `docs/VOICE.md`.
