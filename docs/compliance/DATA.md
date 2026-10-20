# Data statement

- All match data in this repository is synthetic. It is produced by `packages/sim` from a seeded random generator and a tactical brief.
- All clubs and players are fictional. No real Premier League clubs, players, crests, marks or match data are used, included or redistributed, in line with section 4.7 of the Official Rules.
- No match footage is used.
- Calibration targets (for example typical pass completion or xG per shot) are aggregate ranges. If any range is derived from public open data, the source and licence are listed below, and no source events are committed to this repository.

## Calibration sources

Generated from `packages/sim/calibration/targets.yaml`. Only league-level aggregates are used. The sources name real clubs only in their own tables; no club or player names, and no source data, are stored in this repository. Checked Oct 19.

| Metric | Band | Reference mean | Status | Source |
| --- | --- | --- | --- | --- |
| `passes` | 360 to 600 count | 437 | sourced | playerstats.football, Premier League 2025/26 team passes per match (league mean of 20 teams; team range about 364-588). https://playerstats.football/premier-league/stats/passes/previous |
| `pass_completion` | 0.78 to 0.89 ratio | 0.825 | derived | Accurate passes 360.5 / passes 437 per team per match, same site and season (team range about 79-88%). https://playerstats.football/premier-league/stats/accurate-passes/previous |
| `mean_pass_length` | 17 to 22 m | 19.5 | sourced | CIES Football Observatory, 'Length of passes: the best like it short' (InStat data, 35 European leagues; team averages 15.9-23.4 m, league averages about 18.9-21.1 m). https://football-observatory.com/Length-of-passes-the-best-like-it-short |
| `progressive_pass_share` | 0.07 to 0.16 ratio | none | provisional | No published league figure found; our definition (10 m closer or into the box) differs from providers'. |
| `shots` | 8 to 18 count | 12.5 | sourced | playerstats.football, Premier League 2025/26 total shots per team per match (team range about 9.4-15.7). https://playerstats.football/premier-league/stats/total-shots/previous |
| `xg_per_team` | 0.4 to 2.8 xg | 1.47 | sourced | playerstats.football, Premier League 2025/26 team xG per match (team range about 0.89-1.92). https://playerstats.football/premier-league/stats/xg/previous |
| `xg_per_match` | 1.5 to 3.8 xg | 2.95 | derived | Twice the team mean above. |
| `xg_per_shot` | 0.08 to 0.17 xg | 0.117 | derived | 1.47 xG / 12.5 shots per team per match, same season. (upper bound widened from 0.15 to 0.17 (Oct 19) because planted penalties and goals on about 10 shots put end_to_end runs at 0.15 to 0.19 whatever the organic tuning) |
| `possession_share` | 0.35 to 0.65 ratio | 0.5 | provisional | By construction for equal default tactics; no external source needed. (share of completed passes) |
| `fouls` | 7 to 15 count | 10.9 | sourced | playerstats.football, Premier League 2025/26 fouls committed per team per match (team range about 9.7-13.1). https://playerstats.football/premier-league/stats/fouls-committed/previous |
| `yellow_cards` | 0 to 5 count | 1.88 | sourced | playerstats.football, Premier League 2025/26 yellow cards per team per match (team range about 1.3-2.6). https://playerstats.football/premier-league/stats/yellow-cards/previous |
| `corners` | 2 to 10 count | 5.42 | sourced | FCTables, Premier League 2024/25 corners per team per match (team range about 2.3-9.0). https://www.fctables.com/england/premier-league/corners/ |
| `back_line_height_out` | 26 to 40 m | 33.5 | derived | FIFA Training Centre, World Cup 2022: goalkeeper 13.1 m from goal line plus 20.4 m from goalkeeper to defensive line, open play. https://www.fifatrainingcentre.com/en/fwc2022/technical-and-tactical-analysis/goalkeeper-height-and-connection-with-the-defensive-line.php ; definition: https://fifatrainingcentre.com/en/fwc2022/efi-metrics/efi-metric--defensive-line-height-and-team-length.php (out of possession, all frames) |
| `back_line_height_in` | 32 to 52 m | none | provisional | No published figure; the shape rules (back line at least 5 m higher in possession than out) carry the realism. |
| `team_length_out` | 22 to 34 m | 27.2 | sourced | FIFA Training Centre, World Cup 2022 mid-block analysis: team lengths 22.5-29.1 m, tournament average about 27.2 m. https://www.fifatrainingcentre.com/en/fwc2022/technical-and-tactical-analysis/controlling-the-game-without-the-ball--the-mid-block-and-compactness.php (out of possession, ball 35 to 85 m from the defending team's goal (the source is a mid-block)) |
| `team_width_out` | 34 to 46 m | 40.1 | sourced | Same FIFA article: widths 38.4-40.75 m, average about 40.1 m. (out of possession, ball 35 to 85 m from the defending team's goal (the source is a mid-block)) |
| `compactness_out` | 450 to 1000 m2 | none | sourced | Opta Analyst, Opta Vision tracking stats: 'high compactness' under 600 m2, 'low' over 900 m2. https://theanalyst.com/articles/opta-vision-stats-tracking-data-premier-league (median outfield convex-hull area, out of possession, all frames; band only, no reference mean) |

## Narrator examples

`voice/examples.yaml` holds 15 example commentary lines used as few-shot examples. Each is written for this project with fictional clubs and players. Lines borrow only the structure of real sources (length, what they lead with, whether a claim comes with evidence); no source text is copied. The source list names real clubs and players, so it is kept outside this repository; entries refer to it by ID (`S01` to `S13`).
