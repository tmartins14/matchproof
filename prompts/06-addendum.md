# Addendum to prompt 06 (same branch, PR #13)

Review findings and one design change. Restate in eight lines or fewer and wait for my go.

## 1. Condensed live playback

At the current speeds (1, 3 or 6 match minutes per real second), consecutive frames on the wire are 6 to 36 match seconds apart. Player movement can't be shown that way. Replace fixed-speed playback with condensed live, like a highlights show.

- **Run ahead with a broadcast delay.**
  - The pipeline (generator, `FactEngine`, `BeatDetector`) runs in a background worker, using `asyncio.to_thread` or a thread feeding an `asyncio.Queue`. It stays `LOOKAHEAD_S = 120` match seconds ahead of playback.
  - Detection is still incremental: a beat is found only when its pattern completes. Because playback trails by 120 s, the stream knows a moment is coming before the viewer reaches it.
  - This also fixes the event-loop block. Nothing CPU-heavy runs on the event loop.
- **Cruise:** between focus windows, play at `speed` match minutes per real second (1, 3 or 6, as now) and send frames at `WIRE_FPS = 10`.
- **Focus windows:**
  - For each beat with a single anchor moment (goals, `high_turnover_chance`, `big_chance`, `card`), play from `FOCUS_BEFORE_S = 15` s before the anchor to `FOCUS_AFTER_S = 5` s after it at `FOCUS_SPEED = 1` match second per real second, sending every 5 Hz frame.
  - Merge windows that overlap.
  - Span beats (`territorial_spell`, follow-up `momentum_swing`) get no focus window; they appear in the feed when detected.
- **Freeze:** at each anchor, send its freeze frame as a `frame` message, then hold for `FREEZE_HOLD_S = 6` real seconds before continuing.
- **Schema:** extend the `status` state enum with `focus` and `freeze`. A `freeze` status carries the anchor `event_id`; a `focus` status carries nothing about the upcoming beat, so the screen doesn't give it away. Run `make gen`.
- **Resume** with `Last-Event-ID` must still produce identical content.
- **Report:** the real duration of a full match at speeds 1, 3 and 6 for `red_card_flip` seed 3 and `end_to_end` seed 1 (target about 6–10 minutes at speed 3), and the frames sent inside versus outside focus windows.

## 2. Follow-up beats are detected, not planted

A follow-up `momentum_swing` copies `origin: planted` from its anchor. The brief scripted the red card; the 7 m drop afterwards came out of the shape model. So follow-ups get `origin: detected` and no `planted_beat_id`. The link to what caused them is already their `anchor_event_id`.

## 3. One beat per anchor event; add `high_turnover_goal`

- **Add `high_turnover_goal`** to the beat kind enum. The storyline plants it. Run `make gen`.
- **One beat per anchor event.** When several kinds match one shot, keep the most specific, in this order:
  1. `counter_goal`, `set_piece_goal`, `high_turnover_goal`
  2. `open_play_goal`
  3. `high_turnover_chance`
  4. `big_chance`

  Merge the losing candidates' `fact_ids` into the winner.
- **Test:** no two beats share an anchor event, except a follow-up `momentum_swing` with its anchor. On `late_comeback` and `end_to_end`, the planted high-turnover goal is exactly one `high_turnover_goal` beat with `origin: planted`.

## 4. Minimum span for follow-ups

Skip a follow-up whose "since" span is shorter than `MIN_SINCE_S = 480` (8 minutes), for example after a goal in stoppage time. Test it with the `end_to_end` 90+7′ goal.

## 5. Persist the facts that beats cite

`intel beats` must write every fact a beat cites, including the on-demand `since()` facts, to `<match_id>.facts.jsonl`. Re-run the extractors first if that file is missing.

**Test:** every `fact_id` in `beats.jsonl` exists in `facts.jsonl`, on two storylines. The cached replay depends on that chain.

## Verification

- `make lint typecheck test` is green.
- `intel beats` output for `late_comeback` seed 4 and `end_to_end` seed 1.
- The durations and frame counts from part 1.
- `curl -N` output around the red card in `red_card_flip` seed 3: the `focus` status, consecutive frames 0.2 s apart in match time, the `freeze` status with its frame, then the beat.
- Peak memory for one stream (Python's `resource` max RSS is fine).
