# Addendum to prompt 05 (same branch `feat/extractors`, same PR)

Review findings. Restate in five lines or fewer and wait for my go.

## 1. One definition per measure: the median, everywhere

Calibration (`sim/calibrate.py`) aggregates sampled frames with the **median**. The positional facts (`_mean` in `intel/extract_positions.py`, and the spans in `intel/since.py`) use the **mean**. So the same measure gets two numbers. Ashford's out-of-possession compactness before the red card in `red_card_flip` seed 3 is about 934 m² in calibration and 1,055 m² as a fact.

- Add one shared constant, `POSITION_AGGREGATE = "median"`, plus one helper that applies it. Put both in `sim/geometry.py` next to the measures, and use them in calibration, in the window facts and in `since()`. Remove `_mean` for positional measures.
- **Test:** for one match, the match-level out-of-possession compactness and back-line height from calibration equal the facts for the same span, to the rounding of the display.

## 2. Replace ex-15 with a scorer correction the schema supports

The event schema has no deflection, so ex-15 (`fx-1502`) can't be produced. Replace it with a wrong-scorer correction.

- **New metric `shot.shooter`:** the value is the shooter's name, the unit is `""`, and the sources are the shot event.
  - Names come from the brief's roster. Give `extract_all` and `FactEngine` an optional `roster: dict[str, str]` (player id to name), and have the CLI pass it from `<match_id>.brief.json`.
  - With no roster, the value is the player id.
- **Replace the `ex-15` entry in `voice/examples.yaml` with exactly this:**
  ```yaml
  - id: ex-15
    beat_kind: open_play_goal
    mode: fan
    lang: en
    facts:
      - { id: fx-1501, display: "Varga" }
      - { id: fx-1502, display: "goal" }
    line: "Varga scores for Rivermouth."
    amended_from: "Okoro scores for Rivermouth."
    reason: "The shot event names Varga as the shooter, not Okoro."
    source: adapted
    source_ref: S13
  ```
- **In the coverage table**, map `fx-1501` to `shot.shooter` and `fx-1502` to `shot.outcome`. Make `KNOWN_GAPS` empty, and keep the test that fails if any example fact has no extractor.

## Verification

- `make lint typecheck test` is green.
- The `since()` output for the red card in `red_card_flip` seed 3, 30 minutes after the card, Ashford only: back-line height and compactness before and since, plus both change facts. Expect roughly a 7 m back-line drop and about a 15–20% smaller area.
- The coverage table printout with no gaps.

## Out of scope

Filtering which facts are streamed or exposed through MCP (Wednesday), and any change to the generator or shape model.
