# Hyperframes Composition Brief: Matchproof

## Objective
Create a short hackathon-demo-intro brag video for Matchproof (Narrator Trials).

## Output
- Composition directory: `brag-output/composition/`
- Rendered video: `brag-output/brag.mp4`
- Format: landscape — 1920x1080
- Duration: ~20.7s

## Source Material
- Project root: /Users/tylermartins/Documents/portfolio/matchproof
- Primary files read: README.md, docs/DEMO.md, docs/DESIGN.md, docs/screenshots/submission/{table,compare-overturned-names}.png
- Product name: Matchproof — Narrator Trials
- Tagline / strongest claim: "You want an AI narrator? It has to pass this test first."
- Key UI or visual moment to recreate: the Compare view of the 61' red card (OVERTURNED stamp) and the league table rows
- Copy that must appear verbatim:
  - You want an AI narrator?
  - It has to pass this test first.
  - Six narrators. One exam.
  - Same moment. 6 narrators. One referee.
  - Abernathy is sent off with a red. Ashford Vale are down to 10.
  - Named Abernathy without citing the fact that names him.
  - grok-4.7 246 / gpt-4.1 217 / gpt-5.4-mini 169 / gpt-5-mini 119
  - Four of six cleared for air.

## Creative Direction
- Tone preset: polished
- Creative direction: hackathon demo intro
- Interpretation: structured, confident, problem → proof → result; fast-in then hold; no extra jokes.
- Angle: see brag-plan.md
- Hook: the two-line README headline
- Outro / punchline: "Four of six cleared for air." then the lockup and the live URL
- Avoid: generic SaaS language, abstract filler, redesigning the product's look, real club or player names

## Visual Identity
- Background: #0B4F8A
- Text: #FFFFFF
- Accent: #D7F35B (lime); #FF5A4E only for OVERTURNED; #FF9A3C for AMENDED
- Display font: Archivo Narrow 600/700 caps (files in apps/web/src/app/fonts)
- Body font: Archivo
- Visual references: angled cut chips, verdict stamps, lime sweep, ocean-blue panels (#073A69)

## Storyboard
Use brag-plan.md as the creative contract.

1. Hook — 4.4s
2. The exam — 4.34s (traps one by one)
3. The referee — 5.46s (CHECKING → OVERTURNED)
4. The table — 3.27s (rows on beats)
5. Outro — 3.28s

## Audio
- Audio role: sparse professional accents
- Audio arc: soft bed, small motion-matched accents, one dry hit on the verdict, one bell on the lockup
- Music: happy-beats-business-moves-vol-12-by-ende-dot-app.mp3 (already copied to `composition/assets/music/`)
- Music treatment: volume ~0.30, 0.4s fade-in, fade-out over the last 1.5s
- Music cue guidance: preset `<skill-dir>/assets/music/cues/happy-beats-business-moves-vol-12-by-ende-dot-app.music-cues.json`; strong cues 8.74, 13.11, 17.47; beat grid 14.20, 14.73, 15.29, 15.84
- Audio-reactive treatment: subtle; lime sweep and panel glow
- Audio-coupled moments: trap cards, verdict stamp, table rows, lockup
- SFX analysis guidance: `<skill-dir>/assets/sfx/sfx-analysis.md`; pick low high-frequency-risk files
- Exact SFX choice: Hyperframes chooses
- Audio files: copy into `composition/assets/`

## Hyperframes Instructions
Per /brag step-3: load the hyperframes, hyperframes-registry, media-use and hyperframes-cli skills; skip storyline, SPEC.md, usage, history, feedback and REVIEW.md steps; `check` is the gate.

Requirements:
- Show real UI, copy and visual elements from the project.
- Keep all text readable.
- Keep the video within 15-25 seconds.
- Include the planned audio layer.
- Run `hyperframes check` before render.
- Keep creation and rendering local.
