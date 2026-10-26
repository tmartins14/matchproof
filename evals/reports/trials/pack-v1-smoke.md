# Narrator Trials, pack-v1

Run 2026-10-26T12:18:08Z at 23c7f64. Judge gpt-5-mini, auditor judge-grok (grok-4.7). Referee cost: 0.1095 USD.

| # | Candidate | Pts | Clean | Stands | Amended | Overturned | Held | p90 | On-air p90 | USD/match | Auditor agrees | Split | |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | gpt-5-mini | 28 | 50.0% | 9 | 7 | 2 | 0 | 2320 ms | 7914 ms | 0.0203 | 86% | 0/1 | Cleared for air |
| 2 | gpt-5-nano | -34 | 11.1% | 2 | 2 | 14 | 0 | 2297 ms | 7904 ms | prices not set | 100% | 2/7 | Not cleared for air |

## Errors

- gpt-5-nano fx-01: bt-000970-big_chance: ValueError(put_claims rejected claims: [{'index': 0, 'claim_id': 'cl-000970-big_chance-01', 'accepted': False, 'errors': ['Unknown fact id fx-shot-ev-000970-seconds.']}])
- gpt-5-nano fx-01: bt-001100-high_turnover_chance: ValueError(put_claims rejected claims: [{'index': 0, 'claim_id': 'cl-001100-high_turnover_chance-01', 'accepted': False, 'errors': ['Unknown fact id fx-shot-ev-001100-min.']}])

## Overturned

- **gpt-5-mini** fx-01 76′: Rivermouth have taken over since the red card, owning 60% of the ball while Ashford Vale are defending 27 metres deeper than before. [overclaim] 'deeper' compares, but no before or change fact is cited.
- **gpt-5-mini** fx-01 89′: Rivermouth lead 1–0 and have kept 74% of the ball since the goal, starving Ashford of possession. [overclaim] Judge (overclaim): 'have taken control' asserts dominance not supported by possession percentage alone.
- **gpt-5-nano** fx-01 24′: Rivermouth win it in 24′ and Pryce shoots, blocked on the line, the move still alive. [names] The player "Pryce" is not named by any cited fact.
- **gpt-5-nano** fx-01 33′: Rivermouth press Ashford Vale high and win it back in the Ashford half, and Rivermouth stay on top of the move. [overclaim] Judge (overclaim): Facts show Rivermouth had 0 high turnovers (no high presses won) and only 42% share in opposition half, so claiming they 'press Ashford Vale high' and 'win it back in the Ashford half' overstates their control and an event not supported by the turnover fact.
- **gpt-5-nano** fx-01 42′: Ashford Vale have a big chance as Kowal shoots at 42′, a 0.3 xG moment that nearly changes the game. [citation] Unknown fact id fx-shot-ev-000970-seconds.
- **gpt-5-nano** fx-01 43′ [split]: Ashford Vale push at 43′ as Throgmorton drives a 0.3 xG chance wide from the move. [names] Cited fact fx-sequence-ev-000996-shooter is not in the beat's fact bundle.; The player "Throgmorton" is not named by any cited fact.
- **gpt-5-nano** fx-01 46′: Rivermouth attack ends with Pryce shooting true at 45+1′, saved on the line. [numbers] The number "6" matches no display rendering of the cited facts.; The number "0.3" matches no display rendering of the cited facts.; The player "Pryce" is not named by any cited fact.
- **gpt-5-nano** fx-01 48′ (not scored): Rivermouth have 57% possession in the last spell as Ashford Vale defend in their half. [overclaim] Judge (overclaim): Fact gives Ashford Vale share of play in the opposition half (45%), not that they are defending in their half, so 'defend in their half' overclaims area/role.
- **gpt-5-nano** fx-01 48′: Rivermouth win the ball in the 39-m zone and Whitcombe fires a 11-second move, low xG 0.10, but the shot misses wide. [citation] Unknown fact id fx-shot-ev-001100-min.
- **gpt-5-nano** fx-01 71′: Rivermouth dominate the spell, 72% of the ball in the latest stretch. [overclaim] Judge (motive): 'push for a breakthrough' attributes intent/motive not stated in the facts.
- **gpt-5-nano** fx-01 74′: Rivermouth take the lead as Whitcombe fires in from 12 seconds, a 0.2 xG chance. [numbers] Cited fact fx-sh... is not in the beat's fact bundle.; The number "12" matches no display rendering of the cited facts.; The number "74′" matches no display rendering of the cited facts.; The number "1" matches no display rendering of the cited facts.; The number "0" matches no display rendering of the cited facts.; The player "Whitcombe" is not named by any cited fact.
- **gpt-5-nano** fx-01 76′: Rivermouth take 60% of the ball since the red card, Ashford Vale defend deeper, and Rivermouth push to a sharper shape. [overclaim] Judge (unsupported_cause): Saying Rivermouth 'stay compact after the red card' asserts a defensive shape consequence not supported by possession facts; only possession percentages since the red card are given.
- **gpt-5-nano** fx-01 78′: Rivermouth move at 78′, Fenwick-Ode shoots from 26 metres after 8 seconds, and the shot is on target. [names] The player "Fenwick-Ode" is not named by any cited fact.
- **gpt-5-nano** fx-01 87′ [split]: Rivermouth finish from Quain seals the move at 87′. [overclaim] Judge (overclaim): Calling the build-up "smartly" and the finish "clean" evaluates how they were done, which the facts do not measure.
- **gpt-5-nano** fx-01 89′: Ashford Vale win it high up and Throgmorton shoots wide from 30 metres, 89′ move. [names] The player "Throgmorton" is not named by any cited fact.
- **gpt-5-nano** fx-01 89′ (not scored): The shot finishes 0.08 xG quality, a late warning for Rivermouth. [overclaim] Judge (overclaim): Calling it "a late warning for Rivermouth" attributes an effect/impact on Rivermouth not stated by the shot xG and minute facts.
- **gpt-5-nano** fx-01 94′: Rivermouth win it high up and Pryce shoots at 90+4′, a 0.10 xG chance. [overclaim] Judge (motive): Saying 'win it high up' attributes intention/possession action beyond the facts; the facts only show a shot event and its details, not that Rivermouth 'won' the ball high up.
- **gpt-5-nano** fx-01 98′: Ashford Vale win it high up and Dunmore shoots at 90+8′, a 0.23 xG chance. [overclaim] Judge (overclaim): 'win it high up' claims location/pressure not supported by the facts (they only show a shot and freeze-frame counts).
- **gpt-5-nano** fx-01 99′ (not scored): Ashford Vale push to respond as their share falls to 44% in the chase. [overclaim] Judge (motive): 'push to respond' attributes intent/motive not stated in the facts.
