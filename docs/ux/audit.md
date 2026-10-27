# Narrator Trials: first-time judge UX audit (before)

Site: https://gray-sand-08c45ef0f.2.azurestaticapps.net/  ·  Run: 2026-10-26/27, headless Chromium via Playwright, deployed site only (no source read).
Script: `docs/ux/audit-checks.mjs` (re-runnable: `node audit-checks.mjs <url> --out audit-after.json`). Raw output: `docs/ux/audit-before.json`.
Layout checks ran on **all 88 crawled pages** (/, /fixtures, /desk, 85 /compare pages; 393 internal URLs resolved) at 1440, 1280, 1024, 768 and 390.

## 1. Findings

Severity: blocker = cannot complete a task or broken/misleading content; major = likely confusion, clipped/overlapping content, axe serious; minor = polish.

| id | page | viewport | sev | what's wrong | screenshot | suggested fix |
|---|---|---|---|---|---|---|
| F01 | Table (/) | 1280 | major | Header wraps: the DESK tab drops to a second row and its bottom is cut off by the 72 px bar (header content 80 px tall inside a 68 px box). Same page: the "USE ON DESK" button (the main call to action) is cut off at the right edge of the table, which scrolls sideways inside its box with no scroll cue (table needs 1272 px, has 1225). | audit/f01-table-header-wrap-and-clipped-button-1280.png | Let the bar grow (min-height, not fixed height) or shrink the nav gap at 1280; make the table fit at 1280 (drop a column or tighten padding); sticky action column or visible scroll shadow. |
| F02 | Table (/) | 1024, 768 | major | Between about 1100 and 600 px the table silently hides everything right of CLEAN: TRAPS, P90, $/MATCH, FAIL PROFILE and the USE ON DESK button are only reachable by scrolling an inner container with no visible cue. TRAPS is the number the headline relies on. At 1024 and 768 a judge cannot find "Use on Desk" or the traps column. | audit/f02-table-hidden-columns-768.png | Switch to the stacked card layout (as at 390) below about 1300 px, or keep TRAPS and the action visible and move the rest to a detail row. |
| F03 | Fixtures (/fixtures) | 390, 768 | major | The exam grid is a horizontal scroller (760 px in 343 px / 713 px). At 390 only GPT-5-MINI and half of a column show; GPT-5-NANO, GROK-4.7 and PHI-4-MINI are invisible with no scroll hint. A phone judge cannot do T3 from here. | audit/f03-fixtures-grid-hidden-narrators-390.png | Stack per fixture on narrow screens (narrator rows inside each fixture card) or add a scroll hint and a sticky fixture column. |
| F04 | Compare (/compare/fx-01/bt-001962-momentum_swing) | 1024 | major | Page-level horizontal scroll (1061 > 1024). Cause: the unbroken "Unknown fact id fx-possession_share_home_since_ev_001962_to_t5774_54" string in phi-4-mini's card overflows the card and the page. | audit/f04-compare-longid-hscroll-1024.png | `overflow-wrap:anywhere` on fact IDs and refusal messages. |
| F05 | Desk (/desk) | 1280, 1024, 768 | major | axe serious: colour contrast failure on the "Key moments appear here..." paragraph (1, 2 and 4 nodes) because it sits over the bright diagonal yellow stripe. The stripe also runs across the right edge of the KPI cards at 1280. axe moderate (all widths): two banner landmarks (the Desk has its own header besides the site bar) and non-unique landmarks. | audit/f05-desk-banner-contrast-stripe-1280.png | Drop or lower the stripe behind text, or give the column a solid background; make the Desk status strip a `div`/`section`, not a `header`. |
| F06 | Compare (fx-06 90+7 late winner; also fx-01 61') | all | major | The overturn reason contradicts what is on the page. gpt-5-nano is OVERTURNED with "The player 'Haldane' is not named by any cited fact", yet "shooter: Haldane" is the first fact listed. Same for gpt-5-mini / "Abernathy" (fx-01 61', the Table's "worst moment"). phi-4-mini is overturned for "9" matching no rendering although "9 m" is a listed fact (the real fault is that it named the wrong player, Varga). A first-time judge reads this as the referee being wrong. | audit/f06-compare-overturn-reason-contradicts-facts-390.png | Say which fact the narrator cited (e.g. "cited fx-X, which does not name Haldane; the shooter fact is fx-Y, not cited"), and show the cited fact IDs on the card. |
| F07 | Table vs Compare | 1440 | major | The Table's "worst" quote for gpt-5-nano ("number 45 matches no display rendering", Fixture 03, 90+8') does not match the reason on the Compare page it links to ("Cited fact fx-shot-ev-002199-seconds is not in the beat's fact bundle"). Two different explanations for the same overturn, and "45" is a correct fact (45 seconds). | audit/f07-table-vs-compare-reason-mismatch-1440.png | Use the same stored reason string in both places. |
| F08 | Table (/) | all | major | Jargon with no definition at the point of use: "trap" is never defined on the Table (headline says "overturned on 3 of 14 traps"); "referees split on 2" is unexplained; "Clean 43.5%", "overclaim 79%" and the colour bar have no key; the Judge is gpt-5-mini, the same model as the only cleared narrator, with only grok flagged as self-audited; "judge-grok (grok-4.7)" uses a name found nowhere else. | audit/f08-table-jargon-390.png | One-line "Trap = ..." under the headline; tooltip or footnote for split, clean and overclaim; flag the self-judging of gpt-5-mini too. |
| F09 | Desk (/desk) | all | minor | Before anything is run the bar says "DESK · RUNNING GPT-5-MINI (1ST)" with clock 00:00 and "PRE"; the title says running while nothing is. Run narrator is below the fold at 390 (second screen), and 3x speed is preselected with no explanation. Fan/Analyst/Producer and EN/ES are unexplained. | audit/f09-desk-running-label-pre-390.png | "READY: GPT-5-MINI" until Run is pressed; hint text for the audience toggle. |
| F10 | Fixtures, Table, Compare | all | major | Label inconsistency for the fourth outcome: the legend says "NO ANSWER", the Table says "HELD (no answer...)" and Compare says "HELD"; the grid shows only the letters S / A / O / H, and the legend does not map letters to names. Stamps list 85 moments but the grid shows 14 traps, which is not said. | audit/f03-fixtures-grid-hidden-narrators-390.png | Use one word (HELD) everywhere and add a letter key (S/A/O/H) directly above the grid. |
| F11 | Compare | all | minor | Amended narration is shown as a merged redline: copied as text it reads "withscores a 0.8 xG strikefinish in the 90+8′, a dramatic finish90+8′ to themake move.it 3–3". Visually it is struck/inserted, but it is hard to parse, and "0.8 xG" differs from the 0.78 fact. Compare tab lands on fx-01 moment 8 with no pointer to "the worst moment". | audit/f10-compare-diff-text-1440.png | Show "before" and "after" as two lines, or add a toggle. |
| F12 | Compare | 390 | minor | 85 of 85 "SEE THE FIXTURE THIS CAME FROM" links are 307x22 px; the four narrator links in the Table are about 35 px high (target 44). | audit/f06-compare-overturn-reason-contradicts-facts-390.png | Pad to 44 px. |
| F13 | any bad URL | all | minor | Unknown routes (/nope, /compare/fx-09/x, /compare/fx-01/bt-bogus) return the default Azure "404: Not Found / We couldn't find that page" page, with no top bar or way back. | none (text only) | Branded 404 with nav. |

### Status after Part C

| id | sev | status | how |
|---|---|---|---|
| F01 | major | fixed | The run label is hidden at 1360 px and below on every page, so the bar stays one row at 1280; the Table's columns were tightened to fit 1225 px. |
| F02 | major | fixed | Below 1240 px the Table becomes one card per narrator (as at 390), so Traps, p90, $/match and Use on Desk are always visible. |
| F03 | major | fixed | Below 900 px each fixture is a card with every narrator's stamps under its name. |
| F04 | major | fixed | Long ids and refusal messages wrap (`overflow-wrap: anywhere`). |
| F05 | major | fixed | Legend text sits on a solid fill; the Desk strip is a labelled section, not a second banner. |
| F06 | major | fixed | Non-STANDS cards list the facts the claim cited, so "not named by any cited fact" can be checked against the fact list. The reason wording itself is the referee's and is unchanged. |
| F07 | major | fixed | The export now carries one reason line per claim (`claim_reason`); the Table's note is that line cut to length and Compare shows the same line (before, Compare printed the first reason under the bucket label of another). |
| F08 | major | fixed | The hero says what a trap is; the Referee card says gpt-5-mini also judges; a key under the Table explains Clean, Referees split and Fail profile. |
| F09 | minor | fixed | The Desk reads "DESK · READY · <model>" until Run is pressed and "RUNNING" only during a run; the speed control is labelled "Match pace" (Slow · 1 min/s, Normal · 3 min/s, Fast · 6 min/s) with a tooltip. |
| F10 | major | fixed | HELD is the one word everywhere; the Fixtures note maps S, A, O, H and says the grid shows the 14 trap moments. |
| F11 | minor | open | Amended redline reads badly as copied text. |
| F12 | minor | fixed | Text links are 44 px tall (checked at 390 on the sample). |
| F13 | minor | fixed | Unknown routes show a branded 404 with the top bar and a link home (`not-found.tsx`; `staticwebapp.config.json` rewrites 404 to `/404.html`). |

Also in Part C, at the user's request: the Desk's angled-stripe backdrop now sits behind every page, below the top bar.

Not a finding: the nav top bar is identical (same box) on all 88 pages at each width. 72 px tall at 1440 and 1280, 148 px at 1024, 768 and 390 (two rows, by design). No broken internal links, no console errors, no failed requests (hundreds of `net::ERR_ABORTED` prefetches are Next.js link-prefetch noise and are counted separately).

## 2. Tasks (as a first-time judge, page text only)

**T1. Which narrator would you put on air, and why? Success: yes. Clicks: 0** (answer is the headline on `/`: "Cleared for air: gpt-5-mini, overturned on 3 of 14 traps"; 1 more click on "Use on Desk" if you want to act on it).
Hesitations: "traps" and "overturned" mean nothing yet; I read "3 of 14" before I knew what 14 was. "Referees split on 2" read as an error. gpt-5-mini has more AMENDED (38) than STANDS (37) and only 43.5% clean, so "cleared" feels generous until the relegation rule is read at the bottom. The Judge is also gpt-5-mini (F08). Screenshot: audit/f08-table-jargon-390.png. At 768/1024 the Use on Desk button is not visible (F02) and at 1280 it is cut off (F01).

**T2. Find a moment where gpt-5-nano was overturned and say why. Success: yes. Clicks: 1** (nano's row on the Table, link goes to Fixture 03 90+8'). Reason shown: "Cited fact fx-shot-ev-002199-seconds is not in the beat's fact bundle", auditor "not audited". Hesitation: the row's own text says the worst moment is "the number 45 matches no display rendering", which is a different reason for the same moment (F07), and "not in the beat's fact bundle" needs the reader to know what a bundle is. Screenshot: audit/f07-table-vs-compare-reason-mismatch-1440.png.

**T3. Open fixture 06's late winner and compare how each narrator called it. Success: yes at 1440, hard at 390. Clicks: 2** (Fixtures, then the stamp in the "LATE WINNER 90+7'" column, row 06). Result: mini STANDS ("Haldane scores...3-2"), nano OVERTURNED ("Haldane not named by any cited fact"), grok STANDS (30.6 s), phi OVERTURNED (names "Varga", wrong player). Hesitations: with 24 coloured letters in the grid I first looked for the late winner in the 06 row by minute, and the "H" stamp is not in the legend (F10). At 390 the nano, grok and phi columns are off screen with no cue (F03), so I would have had to go via the Compare tab and dropdown (3+ clicks). The overturn reasons contradict the fact list (F06). Screenshots: audit/f03-fixtures-grid-hidden-narrators-390.png, audit/f06-compare-overturn-reason-contradicts-facts-390.png.

**T4. Put the cleared narrator on the Desk and watch until its first verdict lands. Success: yes (live worked; no cached replay needed). Clicks: 2** (Use on Desk, then Run narrator). Timing: clock ran from 00:00; first key moment and first verdict ("1 stands, +3 pts", Checker 1) appeared about 25 s after pressing Run at the default 3x speed (match clock about 25:00). Hesitations: the page already said "RUNNING" before I pressed anything (F09); "Run narrator" is below the first screen at 390; "Analyst / Fan / Producer" and "EN/ES" were unexplained; during the first 20 s the panel said "WAITING FOR THE FIRST KEY MOMENT" with zero counters, which looked stalled. Screenshots: audit/t4-desk-initial-1440.png, audit/t4-desk-running-1440.png, audit/t4-desk-after-1440.png, audit/f09-desk-running-label-pre-390.png.

**T5. What is a trap, and how many did gpt-5-mini fall for? Success: partly. Clicks: 1** (to Fixtures). Answer: 3 of 14 (Table, TRAPS column; grid agrees: fx-01 61' and 87', fx-05 56'). "Trap" is never defined on the Table. On Fixtures it is only implied: "Each one plants a trap" and "the moments the match must contain"; a trap is a planted key moment (red card, late winner...) where a narrator's claim is likely to be wrong. "Fall for" is not mapped to a stamp; I had to infer it means OVERTURNED (F08). Screenshot: audit/f08-table-jargon-390.png.

## 3. Automated checks (88 pages per viewport, counts are totals across pages)

| check | 1440 | 1280 | 1024 | 768 | 390 |
|---|---|---|---|---|---|
| pages with horizontal page scroll | 0 | 0 | 1 (F04) | 0 | 0 |
| inner scroll containers hiding content | 0 | 1 (F01) | 1 (F02) | 2 (F02, F03) | 1 (F03) |
| clipped text elements (overflow hidden) | 9 | 97 | 9 | 9 | 9 |
| overlapping text boxes (>1 px, >35% of line height) | 0 | 0 | 0 | 0 | 0 |
| tap targets under 44x44 | n/a | n/a | n/a | n/a | 89 (F12) |
| axe serious/critical (nodes) | 0 | 1 | 2 | 4 | 0 |
| axe moderate (nodes) | 2 | 2 | 2 | 2 | 2 |
| console errors | 0 | 0 | 0 | 0 | 0 |
| failed requests / HTTP >=400 | 0 | 0 | 0 | 0 | 0 |
| top bar box identical on all pages | yes 1425x72 | yes 1265x72 | yes 1009x148 | yes 753x148 | yes 375x148 |
| broken internal links (393 URLs) | 0 | 0 | 0 | 0 | 0 |

Notes on the counts. Clipped text: the 9 baseline are `div.mp-pitch` freeze-frame captions on compare pages (pitch overflow hidden, caption slightly beyond the box, visually fine) and the Desk root container; the 88 extra at 1280 are the top bar (F01). Overlap: a first pass flagged 670 to 862 pairs, all of them adjacent line boxes of inline insert/delete redlines; after requiring overlap above 35% of line height there were 0, and none were visible in screenshots, so no real text overlap was found. Axe serious/critical are all the Desk contrast issue (F05); axe moderate are the Desk duplicate banner and landmark rules.

## 4. After Part C (redeployed site, full run)

Same script, same 88 pages (`docs/ux/audit-checks.mjs`, raw output `audit-after.json`), against the site redeployed from `main` at `335710a`. Before figures are section 3.

| check (totals across 88 pages) | width | before | after |
|---|---|---|---|
| pages with horizontal page scroll | 1024 | 1 | 0 |
| inner scroll containers hiding content | 1440 / 1280 / 1024 / 768 / 390 | 0 / 1 / 1 / 2 / 1 | 0 / 0 / 0 / 0 / 0 |
| overlapping text boxes | all | 0 | 0 |
| tap targets under 44x44 | 390 | 89 | 0 |
| axe serious/critical (nodes) | 1440 / 1280 / 1024 / 768 / 390 | 0 / 1 / 2 / 4 / 0 | 0 / 0 / 0 / 0 / 0 |
| axe moderate (nodes) | all | 2 | 0 |
| console errors, failed requests, HTTP >= 400 | all | 0 | 0 |
| broken internal links | all | 0 | 0 |
| top bar box identical on every page | all | yes | yes (1425x72 at 1440 and 1280-wide 1265x72; 148 high at 1024 and below) |
| clipped text elements | each width | 9 (97 at 1280) | 96 |

The clipped count went up for one reason, and it is not text: every page now sits in `div.mp-root`, the wrapper that clips the shared backdrop's stripes at the page edge (88 pages), plus the same 8 freeze-frame captions that overhang their box by 2 px as before. At 1280 the 88 clipped top-bar elements from F01 are gone.

Deployed screenshots (Table, an AMENDED Compare moment and the Desk, at 1440 and 390): `deployed/`.

Open for Tyler: F11 (minor).
