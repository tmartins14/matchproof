# Brag Plan: Matchproof (Narrator Trials)

## What is this app?
Narrator Trials puts six candidate AI narrator models through the same exam on seeded fake matches with traps planted in them, and one fixed referee checks every claim against computed facts.

## The angle
A hackathon demo intro: the problem stated in one breath, the product doing its job on a real moment, the result, and the event it was built for. The strongest material is the referee catching a narrator in the act. The narrator names a player without citing the fact that names him, and the claim is OVERTURNED even though it is true.

## Hook (first 2-3 seconds)
"You want an AI narrator?" then "It has to pass this test first." (README headline, verbatim). Big white caps on the ocean-blue field with a lime underline sweep.

## Key moments (the middle)
- The exam: three planted traps appear one by one: a red card on the hour, a stoppage-time penalty, a lead that changes hands late.
- The referee at work: Compare view of the 61' red card. gpt-5-mini's claim goes CHECKING, then OVERTURNED stamp, with the note "Named Abernathy without citing the fact that names him." gpt-4.1's claim for the same moment STANDS.
- The league table: grok-4.7 246, gpt-4.1 217, gpt-5.4-mini 169, gpt-5-mini 119 land one by one; gpt-5-nano is not cleared.

## Outro / punchline
"Four of six cleared for air." Then the MATCHPROOF / NARRATOR TRIALS lockup, "Built for the Inside the Game Developer Hackathon", and the live URL.

## User flow worth showing
Table (rank) → Compare (inspect a trap moment, see a verdict land) → Table result (who is cleared for air). Mirrors the nav: 1 RANK, 2 INSPECT, 3 DEPLOY.

## Tone
- Preset: polished
- Creative direction: hackathon demo intro
- Interpretation: confident and structured, problem → proof → result. Clear statements, fast-in then hold, no jokes beyond the product's own. Fictional clubs and players only (Rivermouth, Ashford Vale, Abernathy).

## Format: landscape — 1920x1080
## Duration: ~20.7s

## Visual identity (from the project, docs/DESIGN.md)
- Background: #0B4F8A (surface panels #073A69, raised #0E5D9F, shadow #042848)
- Accent: lime #D7F35B (STANDS / primary), amber #FF9A3C (AMENDED), red #FF5A4E (OVERTURNED only)
- Text: #FFFFFF on blue; muted #D3E5F7; navy ink #0A2540 on white chips
- Display font: Archivo Narrow (600/700, caps); fonts committed under apps/web/src/app/fonts
- Body font: Archivo
- Strongest visual element: angled "cut" chips (MATCHPROOF white, NARRATOR TRIALS lime) and the verdict stamps

## Share copy (draft)
Matchproof: before an AI narrator goes on air, it sits Narrator Trials. Six narrators, one referee, four cleared for air.

## Audio direction
- Role: sparse professional accents
- Music: happy-beats-business-moves-vol-12 (steady and clean, ~110 BPM), volume ~0.30
- Music treatment: starts at 0, fade-in 0.4s, fade-out over the last 1.5s under the outro
- Music cue guidance: preset read (`assets/music/cues/happy-beats-business-moves-vol-12-by-ende-dot-app.music-cues.json`). Strong cues: 8.74s (Scene 3 start), 13.11s (verdict stamp), 17.47s (outro lockup). Beat grid for the table rows: 14.20, 14.73, 15.29, 15.84 (accent ticks every beat; text rows held, see Scene 4).
- Audio-reactive treatment: subtle; music RMS/bass makes the lime sweep and panel glow breathe. No waveform/equalizer visuals.
- SFX posture: sparse, motion-matched
- Audio-coupled moments: trap cards arriving, the stamp landing, table rows, final lockup
- Restraint rule: nothing loud over a verdict; no stacked SFX

## Storyboard

### Scene 1 — Hook — 4.4s
"You want an AI narrator?" holds ~1.8s, then "It has to pass this test first." holds ~2s (about 12 words total, hold is the floor). Lime sweep under the second line.
Sequential/interaction: yes. Two lines, second replaces the first.
Audio intent: quiet confidence
Audio-coupled idea: soft pop on each line
Music: bed fades in
Transition mood: clean → Scene 2

### Scene 2 — The exam — 4.34s (4.40–8.74)
MATCHPROOF white chip + NARRATOR TRIALS lime chip slam in. "Six narrators. One exam." Then three trap cards, one by one, each held to the end of the scene: "A red card on the hour", "A stoppage-time penalty", "A lead that changes hands late". Card reveals every other beat (~1.1s).
Sequential/interaction: yes. Cards arrive one by one; text hold ~0.8s settled minimum, full set holds ~0.8s before the cut.
Audio intent: set-up
Audio-coupled idea: card-place per trap card
Music: bed
Transition mood: hard push, lands on strong cue 8.74s → Scene 3

### Scene 3 — The referee — 5.46s (8.74–14.20)
Compare screen recreated: freeze frame 61' and "Same moment. 6 narrators. One referee." Claim card for gpt-5-mini: "Abernathy is sent off with a red. Ashford Vale are down to 10." Chip CHECKING (white outline), then the OVERTURNED stamp (red) locked to 13.11s, note line "Named Abernathy without citing the fact that names him." A gpt-4.1 card slides alongside with STANDS (lime).
Sequential/interaction: yes. CHECKING → OVERTURNED stamp.
Audio intent: tension then verdict
Audio-coupled idea: click on CHECKING, one dry impact on the stamp
Music: bed
Transition mood: wipe → Scene 4

### Scene 4 — The table — 3.27s (14.20–17.47)
League table rows land on the beat: grok-4.7 246 pts, gpt-4.1 217, gpt-5.4-mini 169, gpt-5-mini 119. Pts count only; the full set holds ~1.2s. The beat reveals are accents (row bar fills), the text is on screen as a set, not read line by line.
Sequential/interaction: yes. Rows slide in one by one.
Audio intent: payoff builds
Audio-coupled idea: soft tick per row
Music: bed
Transition mood: clean → Scene 5

### Scene 5 — Outro — 3.28s (17.47–20.75)
"Four of six cleared for air." lands on 17.47s, then lockup: MATCHPROOF · NARRATOR TRIALS, "Built for the Inside the Game Developer Hackathon", and the live URL on one line.
Sequential/interaction: none
Audio intent: resolve
Audio-coupled idea: one bell on the lockup
Music: fade out under the lockup
Transition mood: none, end card

**Music mood for this video:** steady, clean, corporate-upbeat
**Audio summary:** soft bed, small motion-matched accents, one dry hit on the verdict, one bell on the lockup.

## Grounding notes
Every number and name on screen comes from README.md, docs/DEMO.md or the committed screenshots in docs/screenshots/submission. Nothing about the product is invented. The hackathon name is from README.md.
