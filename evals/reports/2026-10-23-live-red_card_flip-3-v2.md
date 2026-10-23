# Live run v2: red_card_flip seed 3, speed 3, real models

Run 2026-10-23 on branch `fix/live-run-findings` (commits through ce62682) with `make api-dev`, `MODEL_BASE_URL` and `MODEL_DEPLOYMENT_NAME` from `azd env`, and `az login`. The same match as [the first run](2026-10-23-live-red_card_flip-3.md).

Match `m-red-card-flip-3`: 214 s, 3738 messages, last status `full_time`. 11 beats, 12 claims, 0 sent as `checking`.

## Against the targets
| | first run | this run | target |
|---|---|---|---|
| auditor agreement | 0.5 (3 of 6 audited) | **1.0** (11 of 11 audited) | at least 0.8 |
| claims the auditor returned a result for | 6 of 9 | 11 of 12 | |
| model calls in the trace | narrator, producer and auditor only | **all of them**, judge included | all |
| cost line | none | "prices not set" | filled if prices are set |

Read the 1.0 with two caveats. One claim (`cl-000222-high_turnover_chance-01`) has no audit result: `judge-grok` timed out twice at 45 s on the first audit of the run, so counting it as a miss the rate is 11 of 12 = 0.917. And this is one match.

## Step 3. Stream excerpt: the red card and the first goal
Fact id lists cut to 5. Both goal claims carry the score, and every claim was settled before its beat aired.

```json
{"seq": 2161, "type": "beat", "id": "bt-001484-card", "kind": "card", "label": "63′", "rank": 2}
{"seq": 2162, "type": "claim", "id": "cl-001484-card-01", "text": "Okafor-Lind is shown a second yellow and is sent off.", "verdict": "verified", "fact_ids": ["fx-card-ev-001484-kind", "fx-card-ev-001484-player"], "checker": {"reconciled": true, "judge_supported": true, "retries": 0}}
{"seq": 2163, "type": "claim", "id": "cl-001484-card-02", "text": "Ashford Vale are down to 10 players.", "verdict": "verified", "fact_ids": ["fx-card-ev-001484-players_after"], "checker": {"reconciled": true, "judge_supported": true, "retries": 0}}
{"seq": 2497, "type": "beat", "id": "bt-001670-open_play_goal", "kind": "open_play_goal", "label": "71′", "rank": 3}
{"seq": 2498, "type": "claim", "id": "cl-001670-open_play_goal-01", "text": "Pryce scores for Rivermouth after a 16 s, four-pass move to put them 1–0.", "verdict": "rephrased", "fact_ids": ["fx-shot-ev-001670-shooter", "fx-sequence-ev-001670-seconds", "fx-sequence-ev-001670-passes", "fx-score_after-ev-001670"], "checker": {"reconciled": true, "judge_supported": true, "retries": 1}}
{"seq": 2499, "type": "claim", "id": "cl-001670-open_play_goal-02", "text": "He had 4 metres to the nearest defender as he pulled the trigger for a 0.10 xG strike.", "verdict": "verified", "fact_ids": ["fx-freeze_frame-ev-001670-shooter_nearest_defender", "fx-shot-ev-001670-xg", "fx-shot-ev-001670-outcome"], "checker": {"reconciled": true, "judge_supported": true, "retries": 0}}
{"seq": 2515, "type": "verdict", "id": "cl-001670-open_play_goal-01", "text": "Pryce scores for Rivermouth after a 16 s, four-pass move to put them 1–0.", "verdict": "rephrased", "fact_ids": ["fx-shot-ev-001670-shooter", "fx-sequence-ev-001670-seconds", "fx-sequence-ev-001670-passes", "fx-score_after-ev-001670"], "checker": {"reconciled": true, "judge_supported": true, "retries": 1}}
```

All 12 claims as sent:

- verified: Ashford's Bellamy-Cruz fires a 0.30 xG shot after winning the ball 7 m from goal, but it's blocked.
- verified: Okafor-Lind is shown a second yellow and is sent off.
- verified: Ashford Vale are down to 10 players.
- rephrased: Pryce scores for Rivermouth after a 16 s, four-pass move to put them 1–0.
- verified: He had 4 metres to the nearest defender as he pulled the trigger for a 0.10 xG strike.
- verified: Rivermouth win it 32 metres out and Marchetti-Roe fires - it rattles the post, a 0.06 xG chance.
- rephrased: Ashford Vale's back line is 9 m deeper than before the red card.
- rephrased: Their shape has tightened by 204 square metres since the red card.
- rephrased: Pryce fires Rivermouth 2–0 with a finish after a 6-second move in the 86′.
- rephrased: Rivermouth lead 1–0 and their back line has dropped 6 metres since the goal.
- verified: Ashford have 53 per cent of the play in the Rivermouth half and have tightened their shape by 194 square metres since the goal.
- verified: Rivermouth lead 2–0 and Ashford Vale have pushed their back line 4 metres higher since the goal, spreading their shape to 803 square metres.

## Step 4. Producer log

11 beats: 8 narrated, 3 skipped; 6 forced by the hard rules, 5 by the model.

| beat | kind | narrate | rank | decided by | note |
|---|---|---|---|---|---|
| bt-000222-high_turnover_chance | high_turnover_chance | True | 1 | model | Narrate a chance from a high turnover at 9′ for Ashford Vale, notable early swing in momentum |
| bt-000556-high_turnover_chance | high_turnover_chance | False | None | model | Another chance from a high turnover at 23′, similar to earlier one so skip to avoid repetition |
| bt-000993-territorial_spell | territorial_spell | False | None | model | Rivermouth sustained spell of territory noted but adds little new after early chance, skip to preserve variety |
| bt-001484-card | card | True | 2 | forced | The red card at 63′ is always on the feed. |
| bt-001670-open_play_goal | open_play_goal | True | 3 | forced | The goal from open play at 71′ is always on the feed. |
| bt-001796-high_turnover_chance | high_turnover_chance | True | 4 | model | Chance from a high turnover at 77′ for Rivermouth adds a new attacking moment after the goal |
| bt-001484-momentum_swing | momentum_swing | True | 5 | forced | The shift after a goal or red card at 63–78′ is always on the feed. |
| bt-001997-open_play_goal | open_play_goal | True | 6 | forced | The goal from open play at 86′ is always on the feed. |
| bt-001670-momentum_swing | momentum_swing | True | 7 | forced | The shift after a goal or red card at 71–86′ is always on the feed. |
| bt-002282-high_turnover_chance | high_turnover_chance | False | None | model | Late chance from a high turnover at 90+8 not new story and repeats earlier high turnover chances |
| bt-001997-momentum_swing | momentum_swing | True | 8 | forced | The shift after a goal or red card at 86–90+9′ is always on the feed. |

## Step 5. Span tree for one beat (bt-001670-open_play_goal, the first goal)

The `check` span now holds `reconcile`, `lint` and `judge` spans, and the judge span holds its `chat gpt-5-mini` span with token usage. The first draft failed lint, went back through one `retry`, and passed. Audit spans are separate roots linked to the beat. Framework executor spans are shown only where they have children; attributes are shortened.

```
beat  12128 ms  {"match_id": "m-red-card-flip-3", "beat_id": "bt-001670-open_play_goal", "mode": "fan", "beat.latency_ms": 12119, "verdicts": "rephrased,ver
  workflow.run  12120 ms  
    executor.process producer  11 ms  
    executor.process narrator  5545 ms  
    executor.process checker  3174 ms  
    executor.process narrator  1781 ms  
  producer  10 ms  {"agent.name": "producer", "beat_id": "bt-001670-open_play_goal", "narrate": true, "decided_by": "forced"}
    fetch_bundle  10 ms  
  narrate  5544 ms  {"request.model": "gpt-5-mini", "retry": false, "usage.input_tokens": 1926, "usage.output_tokens": 159}
    chat gpt-5-mini  5525 ms  {"system": "az.ai.openai", "request.model": "gpt-5-mini", "usage.input_tokens": 1926, "usage.output_tokens": 159}
  check  3173 ms  {"request.model": "gpt-5-mini"}
    reconcile  0 ms  {"ok": true}
    lint  0 ms  {"ok": false}
    reconcile  0 ms  {"ok": true}
    lint  0 ms  {"ok": true}
    judge  3170 ms  {"request.model": "gpt-5-mini", "usage.input_tokens": 953, "usage.output_tokens": 49, "judge.supported": true}
      chat gpt-5-mini  3169 ms  {"system": "az.ai.openai", "request.model": "gpt-5-mini", "usage.input_tokens": 953, "usage.output_tokens": 49}
  retry  1780 ms  
  narrate  1780 ms  {"request.model": "gpt-5-mini", "retry": true, "usage.input_tokens": 2104, "usage.output_tokens": 89}
    chat gpt-5-mini  1762 ms  {"system": "az.ai.openai", "request.model": "gpt-5-mini", "usage.input_tokens": 2104, "usage.output_tokens": 89}
  check  1598 ms  {"request.model": "gpt-5-mini"}
    reconcile  0 ms  {"ok": true}
    lint  0 ms  {"ok": true}
    judge  1596 ms  {"request.model": "gpt-5-mini", "usage.input_tokens": 982, "usage.output_tokens": 53, "judge.supported": true}
      chat gpt-5-mini  1595 ms  {"system": "az.ai.openai", "request.model": "gpt-5-mini", "usage.input_tokens": 982, "usage.output_tokens": 53}
  put_claims  1 ms  
audit  12301 ms  {"claim_id": "cl-001670-open_play_goal-01", "request.model": "judge-grok", "audit.outcome": "agree"}
  chat judge-grok  12295 ms  {"system": "az.ai.openai", "request.model": "judge-grok", "usage.input_tokens": 1031, "usage.output_tokens": 46}   [linked to the beat span]
audit  15777 ms  {"claim_id": "cl-001670-open_play_goal-02", "request.model": "judge-grok", "audit.outcome": "agree"}
  chat judge-grok  15769 ms  {"system": "az.ai.openai", "request.model": "judge-grok", "usage.input_tokens": 1001, "usage.output_tokens": 42}   [linked to the beat span]
```

## Step 6. Calls and tokens for the match
Tokens are from `GET /health/budget`. They equal the sums of the `chat` spans' usage attributes for every role.

| role | model | calls | input | output | total |
|---|---|---|---|---|---|
| narrator | gpt-5-mini | 12 (8 drafts, 4 retries) | 22790 | 1248 | 24038 |
| judge (inline) | gpt-5-mini | 14 | 13186 | 699 | 13885 |
| auditor | judge-grok | 13 (12 audits; one timed out twice) | 10883 | 458 | 11341 |
| producer | gpt-5-mini | 5 | 1854 | 234 | 2088 |
| **total** | | **44** | | | **51352** |

Cost: **prices not set**. `packages/agents/config/prices.yaml` has null values; fill them in from the Azure pricing pages and `GET /health/budget` and `evals/e2e.py` report the cost. The first run used 44,335 tokens; this one used 51352, with more claims and the judge's calls now all counted in the trace.

## Step 7. Audit summary (GET /matches/{id}/audit)
```json
{
  "match_id": "m-red-card-flip-3",
  "claims_audited": 11,
  "agreement_rate": 1.0,
  "unavailable": 1,
  "skipped_for_token_cap": 0,
  "pending": 0
}
```

No disagreements.
