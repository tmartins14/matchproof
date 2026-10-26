# Narrator Trials, pack-v1

Run 2026-10-26T02:34:51Z at c3e2a3a. Judge gpt-5-mini, auditor judge-grok (grok-4.7). Referee cost: 0.0832 USD.

| # | Candidate | Pts | Clean | Stands | Amended | Overturned | Held | p90 | USD/match | Auditor agrees | |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | gpt-5-mini | 34 | 55.6% | 10 | 7 | 1 | 0 | 9189 ms | 0.0183 | 84% | Cleared for air |
| 2 | gpt-5-nano | -18 | 14.3% | 2 | 3 | 9 | 1 | 8167 ms | prices not set | 83% | Not cleared for air |

## Errors

- gpt-5-nano fx-01: bt-000544-high_turnover_chance: ValueError(put_claims rejected claims: [{'index': 0, 'claim_id': 'cl-000544-high_turnover_chance-01', 'accepted': False, 'errors': ['Unknown fact id fx-freeze_frame-ev-000544-ball_won_distance.']}])
- gpt-5-nano fx-01: bt-000970-big_chance: ValueError(put_claims rejected claims: [{'index': 0, 'claim_id': 'cl-000970-big_chance-01', 'accepted': False, 'errors': ['Unknown fact id fx-shot-ev-000970-shot_clock.']}])
- gpt-5-nano fx-01: bt-001100-high_turnover_chance: ValueError(put_claims rejected claims: [{'index': 1, 'claim_id': 'cl-001100-high_turnover_chance-02', 'accepted': False, 'errors': ['Unknown fact id fx-freeze_frame-ev-001100-ball_won_distance.']}])

## Overturned

- **gpt-5-mini** fx-01 76′: Rivermouth have had 60% of the ball since the red card, turning possession the way of the home side. [overclaim] Judge (overclaim): 'taken control' and 'pinning Ashford back' describe dominance and being pinned which the possession stat alone does not prove.
- **gpt-5-nano** fx-01 33′: Ashford Vale push high up the pitch, Rivermouth press with 100% in the latest spell. [overclaim] Judge (overclaim): Saying Ashford Vale 'hold the ball high up the pitch' states where they are in control (territorial position) but no fact about location or possession in the latest spell is provided.
- **gpt-5-nano** fx-01 33′ (not scored): Ashford Vale have 66% of possession in the spell while Rivermouth stay aggressive. [overclaim] Judge (overclaim): 'Rivermouth keep the pressure up' is a claim about Rivermouth's pressure not supported by possession facts.
- **gpt-5-nano** fx-01 43′ (not scored): Ashford Vale win it and Throgmorton shoots from 43′, a 0.30 xG chance. [overclaim] Judge (overclaim): Calling it 'a quick break' asserts the move was quick, which the facts do not state.
- **gpt-5-nano** fx-01 46′: Rivermouth win it at 45+1 and Pryce tests the keeper, a 0.3 xG effort. [numbers] The number "6" matches no display rendering of the cited facts.
- **gpt-5-nano** fx-01 48′: Rivermouth pressure pays off as they win the ball high, then keep Ashford pegged in their own half. [overclaim] 'deeper' compares, but no before or change fact is cited.
- **gpt-5-nano** fx-01 71′ (not scored): Rivermouth keep 72% of the ball in the latest spell, and Ashford Vale tightens in their own half. [overclaim] Judge (overclaim): 'dominate the spell' asserts control beyond the measured possession share; 72% possession is a figure but 'dominate' is an unmeasured qualitative claim.
- **gpt-5-nano** fx-01 74′: Rivermouth break through Whitcombe, a 12-second move ends in a goal that opens the scoring. [numbers] The number "12" matches no display rendering of the cited facts.; The player "Whitcombe" is not named by any cited fact.
- **gpt-5-nano** fx-01 74′ (not scored): Rivermouth lead as the move finishes with a Whitcombe strike after a 4-pass move and a 77 m sprint from the ball. [names] The player "Whitcombe" is not named by any cited fact.
- **gpt-5-nano** fx-01 78′: Rivermouth attack as Fenwick-Ode shoots after an 8-second move, his effort on target but saved. [names] The player "Fenwick-Ode" is not named by any cited fact.
- **gpt-5-nano** fx-01 89′: Ashford Vale win it 89′ and Throgmorton shoots from 30 metres, a 0.08 xG chance. [overclaim] Judge (overclaim): 'Ashford win it' claims they won the ball but facts only state where the ball was won (distance) and by whom for the shot sequence; it asserts a team-level turnover ('win it') not supported by the cited facts.
- **gpt-5-nano** fx-01 94′: Rivermouth win it 90+4′ and Pryce fires a shot from 25 metres that's blocked. [names] The player "Pryce" is not named by any cited fact.
- **gpt-5-nano** fx-01 98′: Ashford Vale push late, Dunmore's 0.23 xG shot from 10 m is saved to keep Rivermouth level. [names] 'level' compares, but no before or change fact is cited.; The player "Dunmore" is not named by any cited fact.
- **gpt-5-nano** fx-01 99′: Rivermouth lead as the 87th minute passes and the clock drains the last chances. [numbers] The number "87" matches no display rendering of the cited facts.
- **gpt-5-nano** fx-01 99′ (not scored): Rivermouth stay in control with 56% of possession since the goal. [overclaim] Judge (motive): Saying 'Ashford Vale chase in the final minutes' attributes intent/effort not stated by the possession and score facts.
