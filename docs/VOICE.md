# Voice

Matchproof puts text on screen for the whole match. This guide sets how that text reads, and `voice/banned.yaml` enforces the parts a machine can check. Product text means narration and UI copy. If a line sounds like a chatbot, judges stop trusting it, and the verification story gets weaker.

## Register

Live-text football commentary. Present tense. Short: one or two sentences, 30 words at most. Team before player. A number appears only when a fact supplies it.

## Adjectives are claims

"Against the run of play", "dominant", "fading" and "in control" each need a fact behind them: possession, territory, shot share or line height. With no fact, cut the word. The Checker treats an unbacked adjective the way it treats an unbacked number.

## Modes

- **fan:** what happened and why it matters.
- **analyst:** the mechanism: shape, distances, sequences.
- **producer:** a rundown note (clip window, angle, what to show), not commentary.

## Banned patterns

The rules live in `voice/banned.yaml`. Each has an id, a regex, a severity, a scope (`narration`, `ui` or both) and a one-line reason. Errors fail CI and the evals; warnings are reported only. The numbers in the pairs below stand in for fact displays.

| Before | After |
| --- | --- |
| In a dramatic turn of events, Ashford showcase their resilience. | Ashford level it. Their first shot on target since the 30th minute. |
| Rivermouth's press is not just aggressive but relentless. | Rivermouth have won it back in Ashford's third six times since half-time. |
| Ashford seem to be in control, with real dominance in midfield. | Ashford have 62% of the ball in midfield since the restart. |
| What a game-changer! Rivermouth unlock the defence with a seamless move. | Rivermouth go through the middle in 4 passes and Haldane is clear. |
| Rivermouth appear to be fading as the half wears on. | Rivermouth's back line has dropped 7 metres since the hour. |

## On-screen verdict vocabulary

The verdict enum in `claim.schema.json` does not change. These are display labels, mapped in the UI copy files (`apps/web/src/copy/`). The words "AI", "agent", "model" and "generated" never appear in the live desk UI. They are allowed in the dev panel, the docs and the pitch.

| Schema verdict | Label | Meaning shown to the viewer |
| --- | --- | --- |
| `checking` | CHECKING | The pitch highlights the players or zone the claim is about |
| `verified` | STANDS | The claim matches the evidence |
| `rephrased` | AMENDED | Old wording struck through, new wording below, reason on hover |
| `blocked` | OVERTURNED | The claim is withdrawn; the reason is shown |
| `delayed` | HELD | Evidence not in yet; the claim waits |

## Visual rules

No sparkle or magic icons, no gradients, no glow, no typing or streaming-cursor animation, no chat bubbles, no "Thinking…" spinners. While a claim is checking, show the evidence on the pitch instead of a spinner.

## Real-world references

Study real live-text and radio commentary for rhythm, but never paste real lines into the repo. Rewrite with fictional clubs and mark the entry `source: adapted`.
