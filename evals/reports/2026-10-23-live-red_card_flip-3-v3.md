# Live run v3: red_card_flip seed 3, speed 6, real models, corrections by consensus

Run 2026-10-23 on `feat/audit-corrections` with `MODEL_BASE_URL` from `azd env`, `az login`, judge prompt `judge.v3.md`. In process through the API (`TestClient`, real pacer): 198 s, 11 claims. `/health` said `"agents": "ready"`.

## Audit summary (`GET /matches/m-red-card-flip-3/audit`)

| | |
|---|---|
| claims audited | 11 |
| agreement rate | 0.818 (9 of 11) |
| agreement rate after corrections | 0.909 |
| corrections | 1 |
| unresolved | 1 |
| auditor unavailable | 0 |

Tokens for the match: narrator 23,989, judge 21,425, auditor 11,471, producer 2,085. Cost: prices not set.

## The correction (a `verdict` message on the stream, and stored)

`cl-001796-high_turnover_chance-01`, `rephrased`, `correction.at_t` 5090 s, `by` `["judge-grok", "gpt-5-mini"]`.

- previous: Rivermouth win it 32 metres out and Marchetti-Roe fires, hits the post from a low-xG chance.
- new: Rivermouth win it 32 metres out and Marchetti-Roe lashes a shot that hits the post, a 0.06 xG chance.
- reason: "low-xG" is an evaluative adjective; the fact only measures 0.058 xG (writable as 0.06 or 0.1), not that the chance is low.

## The unresolved disagreement

`cl-001484-momentum_swing-01`: "Ashford Vale are defending much deeper since the red card, their back line now 9 m deeper than before."
- judge-grok (overclaim): "much deeper" adds an intensifier the 9 m measurement does not state.
- gpt-5-mini, asked again: the fact states the back line dropped 9 m deeper since the red card; "deeper" and the 9 m figure match it. So nothing changed on screen. This one is arguably the auditor being right ("much"), so it is a candidate eval case: `evals/from_audit.py` prints it.

## Producer log, audit lines

- The second model disagrees on cl-001484-momentum_swing-01 (overclaim): "much deeper" adds an intensifier the 9 m measurement does not state.
- The second model disagrees on cl-001796-high_turnover_chance-01 (overclaim): "low-xG" is an evaluative adjective; ...
- The second model disagrees on cl-001484-momentum_swing-01 (overclaim) but the judge, asked again, keeps it: ...
- cl-001796-high_turnover_chance-01 was corrected after the second model and the judge agreed (overclaim).
