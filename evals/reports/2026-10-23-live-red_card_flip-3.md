# Live run: red_card_flip seed 3, speed 3, real models

Run 2026-10-23 against `main` at f7f7f44 (PR #20 merged), with `make api-dev`, `MODEL_BASE_URL` and `MODEL_DEPLOYMENT_NAME` from `azd env`, and `az login`. No code changed. These are prompt 09 verification steps 3 to 7.

Match `m-red-card-flip-3`: the stream took 214 s, 3736 messages, last status `full_time`. 11 beats, 10 `claim` messages, 5 `verdict` messages, 0 claims sent as `checking`.

## Step 3. Stream excerpt around the red card
`curl -sN "localhost:8000/matches/m-red-card-flip-3/stream?speed=3"`. The beat, then its claim with the final verdict (the check finished before air, so there was no `checking` message), then the next beats. Fact id lists are cut to 4. The last line is the red card's follow-up `momentum_swing` beat; its claim comes later in the stream.

```json
{"seq": 2162, "type": "beat", "id": "bt-001484-card", "kind": "card", "label": "63′", "rank": 2}
{"seq": 2163, "type": "claim", "id": "cl-001484-card-01", "beat_id": "bt-001484-card", "text": "Okafor-Lind is shown a second yellow and sent off; Ashford Vale are down to 10.", "verdict": "verified", "fact_ids": ["fx-card-ev-001484-player", "fx-card-ev-001484-kind", "fx-card-ev-001484-players_after"], "checker": {"reconciled": true, "judge_supported": true, "retries": 0, "model": "gpt-5-mini", "latency_ms": 1611, "trace_id": "270dae6b3ac9ca4594835d8d2f59fe42"}, "span_id": "942d2dcec81d2425"}
{"seq": 2496, "type": "beat", "id": "bt-001670-open_play_goal", "kind": "open_play_goal", "label": "71′", "rank": 3}
{"seq": 2497, "type": "claim", "id": "cl-001670-open_play_goal-01", "beat_id": "bt-001670-open_play_goal", "text": "Rivermouth edge in front as Pryce fires home from inside the move, a 0.10 xG finish minutes after the attack began.", "verdict": "verified", "fact_ids": ["fx-shot-ev-001670-shooter", "fx-shot-ev-001670-outcome", "fx-shot-ev-001670-xg", "fx-sequence-ev-001670-start_clock"], "checker": {"reconciled": true, "judge_supported": true, "retries": 0, "model": "gpt-5-mini", "latency_ms": 1641, "trace_id": "270dae6b3ac9ca4594835d8d2f59fe42"}, "span_id": "a48f5f86fe2cd070"}
{"seq": 2764, "type": "beat", "id": "bt-001796-high_turnover_chance", "kind": "high_turnover_chance", "label": "77′", "rank": 4}
{"seq": 2765, "type": "claim", "id": "cl-001796-high_turnover_chance-01", "beat_id": "bt-001796-high_turnover_chance", "text": "Rivermouth win it 32 metres out and Marchetti-Roe lashes a shot onto the post from a 7 s move, a 0.06 xG chance.", "verdict": "verified", "fact_ids": ["fx-sequence-ev-001796-ball_won_distance", "fx-shot-ev-001796-shooter", "fx-shot-ev-001796-outcome", "fx-sequence-ev-001796-seconds"], "checker": {"reconciled": true, "judge_supported": true, "retries": 0, "model": "gpt-5-mini", "latency_ms": 1529, "trace_id": "270dae6b3ac9ca4594835d8d2f59fe42"}, "span_id": "ada881aafae7fd81"}
{"seq": 2879, "type": "beat", "id": "bt-001484-momentum_swing", "kind": "momentum_swing", "label": "63–78′", "rank": 5}
```

## Step 4. Producer log (GET /matches/{id}/producer-log)

11 beats: 9 narrated, 2 skipped; 6 forced by the hard rules, 5 decided by the model.

| beat | kind | narrate | rank | decided by | note |
|---|---|---|---|---|---|
| bt-000222-high_turnover_chance | high_turnover_chance | True | 1 | model | Narrate a chance after a high turnover at 9′ for Ashford Vale because it introduces an early big opportunity |
| bt-000556-high_turnover_chance | high_turnover_chance | False | None | model | Chance from a high turnover at 23′ repeats an earlier similar chance so skip to avoid repetition |
| bt-000993-territorial_spell | territorial_spell | False | None | model | Rivermouth sustained pressure noted but low salience and repeats general possession theme so skip |
| bt-001484-card | card | True | 2 | forced | The red card at 63′ is always on the feed. |
| bt-001670-open_play_goal | open_play_goal | True | 3 | forced | The goal from open play at 71′ is always on the feed. |
| bt-001796-high_turnover_chance | high_turnover_chance | True | 4 | model | Chance from a high turnover at 77 minutes; adds fresh attacking threat after recent goal |
| bt-001484-momentum_swing | momentum_swing | True | 5 | forced | The shift after a goal or red card at 63–78′ is always on the feed. |
| bt-001997-open_play_goal | open_play_goal | True | 6 | forced | The goal from open play at 86′ is always on the feed. |
| bt-001670-momentum_swing | momentum_swing | True | 7 | forced | The shift after a goal or red card at 71–86′ is always on the feed. |
| bt-002282-high_turnover_chance | high_turnover_chance | True | 8 | model | Late chance from a high turnover at 90+8′ for away merits narration as fresh late drama |
| bt-001997-momentum_swing | momentum_swing | True | 9 | forced | The shift after a goal or red card at 86–90+9′ is always on the feed. |

Audit lines in the same log:

- The second model disagrees on cl-001484-momentum_swing-01 (overclaim): “Tighter” is a comparison the facts do not make; 730 m² is only the area covered, with no baseline showing it got tighter.
- The second model disagrees on cl-001997-open_play_goal-01 (overclaim): “Composed” judges the finish’s manner beyond the goal, 6-second move and 0.14 xG facts.
- The second model disagrees on cl-001670-open_play_goal-01 (overclaim): "Edge in front" says Rivermouth took the lead, but no fact gives the scoreline.

## Step 5. Span tree for one beat (console exporter, bt-001484-card)

One trace for the whole match (trace_id 270dae6b3ac9ca4594835d8d2f59fe42). Durations are wall time. Attributes are shortened.

```
beat  3457 ms  {"match_id": "m-red-card-flip-3", "beat_id": "bt-001484-card", "mode": "fan", "beat.latency_ms": 3448, "verdicts": "verified"}
  workflow.build  0 ms  {"workflow_builder.name": "WorkflowBuilder-67443cda-91e1-49a0-8b4b-a42636349a70", "workflow.id": "3c905e55-9203-419c-886d-ea6119da8519", "workflow.def
  workflow.run  3449 ms  {"workflow.id": "3c905e55-9203-419c-886d-ea6119da8519", "workflow.name": "WorkflowBuilder-67443cda-91e1-49a0-8b4b-a42636349a70"}
    edge_group.process InternalEdgeGroup  0 ms  {"edge_group.type": "InternalEdgeGroup", "edge_group.id": "InternalEdgeGroup/11a5a845-99f0-4a88-9043-ab43fd7518a8", "message.source_id": "internal:pro
    executor.process producer  5 ms  {"executor.id": "producer", "executor.type": "ProducerExecutor", "message.type": "MessageType.STANDARD", "message.payload_type": "WorkflowMessage"}
      message.send  0 ms  {"message.type": "Briefed"}
    edge_group.process SingleEdgeGroup  0 ms  {"edge_group.type": "SingleEdgeGroup", "edge_group.id": "SingleEdgeGroup/23eed8a2-8ce7-48f7-b30a-b85d98f03d69", "message.source_id": "producer", "edge
    executor.process narrator  1824 ms  {"executor.id": "narrator", "executor.type": "NarratorExecutor", "message.type": "MessageType.STANDARD", "message.payload_type": "WorkflowMessage"}
      message.send  0 ms  {"message.type": "Drafted"}
    edge_group.process SingleEdgeGroup  0 ms  {"edge_group.type": "SingleEdgeGroup", "edge_group.id": "SingleEdgeGroup/c07d4359-dd75-4795-9fcd-977cc72ce5a6", "message.source_id": "narrator", "edge
    executor.process checker  1617 ms  {"executor.id": "checker", "executor.type": "CheckerExecutor", "message.type": "MessageType.STANDARD", "message.payload_type": "WorkflowMessage"}
  producer  5 ms  {"agent.name": "producer", "beat_id": "bt-001484-card", "narrate": true, "decided_by": "forced"}
    fetch_bundle  5 ms  
  narrate  1823 ms  {"request.model": "gpt-5-mini", "retry": false, "usage.input_tokens": 1387, "usage.output_tokens": 75}
    chat gpt-5-mini  1805 ms  {"system": "az.ai.openai", "request.model": "gpt-5-mini", "server.address": "ais-oou4h3al.services.ai.azure.com", "usage.input_tokens": 1387, "usage.o
  check  1614 ms  {"request.model": "gpt-5-mini"}
  put_claims  2 ms  
audit  6322 ms  {"claim_id": "cl-001484-card-01", "request.model": "judge-grok", "audit.outcome": "agree"}
  chat judge-grok  6315 ms  {"system": "az.ai.openai", "request.model": "judge-grok", "server.address": "ais-oou4h3al.services.ai.azure.com", "usage.input_tokens": 982, "usage.ou   [linked to the beat span]
```

## Step 6. Model calls and tokens for the match
Tokens are from `GET /health/budget` (the day's counter, which this run started at 0). Calls and the input/output split are from the exported `chat` and `narrate` spans; they add up to the budget figures for the narrator, producer and auditor.

| role | model | calls | tokens (budget) | input / output (spans) |
|---|---|---|---|---|
| narrator | gpt-5-mini | 12 (9 first drafts, 3 retries) | 22502 | 21377 / 1125 |
| judge (inline) | gpt-5-mini | not in the spans | 13308 | not in the spans |
| auditor | judge-grok | 7 (6 audits, 1 retry) | 6440 | 6168 / 272 |
| producer | gpt-5-mini | 5 (the 6 forced beats were not asked) | 2085 | 1854 / 231 |
| **total** | | | **44335** | |

Cost estimate: **not computed**. There is no price table in the repo and I have not looked up current prices, so any dollar figure would be a guess.

## Step 7. Audit summary (GET /matches/{id}/audit)

Agreement rate **0.5** (3 of 6 claims audited). The auditor changed no verdict (log-only). Disagreements:

**cl-001484-momentum_swing-01** (verdict verified): Ashford Vale have dropped 9 m deeper since the red card and are defending in a tighter 730 square metres shape.
- gpt-5-mini: Both the 9 m drop and 730 m² tighter shape for Ashford Vale since the red card are supported by the cited facts.
- judge-grok (overclaim): “Tighter” is a comparison the facts do not make; 730 m² is only the area covered, with no baseline showing it got tighter.

**cl-001997-open_play_goal-01** (verdict verified): Pryce scores for Rivermouth, a composed finish after a 6-second move. 0.14 xG.
- gpt-5-mini: All claims (scorer, team, 6-second move, 0.14 xG, goal) match the facts and use allowed wording.
- judge-grok (overclaim): “Composed” judges the finish’s manner beyond the goal, 6-second move and 0.14 xG facts.

**cl-001670-open_play_goal-01** (verdict verified): Rivermouth edge in front as Pryce fires home from inside the move, a 0.10 xG finish minutes after the attack began.
- gpt-5-mini: All claims match the facts: player, goal, xG and minute are supported; wording is an allowed vivid verb and timing fits.
- judge-grok (overclaim): "Edge in front" says Rivermouth took the lead, but no fact gives the scoreline.

## Findings (nothing was changed)
1. **Spans below `check` are missing.** The `reconcile`, `lint` and `judge` spans described in the docs, and the inline judge's `chat gpt-5-mini` spans, are not in the export. The `check` span has only its model attribute, so the judge's call count and input/output split cannot be read from the trace.
2. **`checking` then `verdict` did not occur live.** Every claim was settled before its beat aired. The 5 `verdict` messages are audit results for claims already on screen. The `checking` path is covered by the fake-model tests only.
3. **The two judges disagree on wording the inline judge passed.** Two are evaluative words (`composed`, `tighter`); the third is "edge in front", which implies a scoreline no fact gives. `composed` is not in the `voice/banned.yaml` adjective list.
4. Cost is missing, as above.
