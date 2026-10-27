# Matchproof: guide for judges

Live site: https://gray-sand-08c45ef0f.2.azurestaticapps.net/

## 3-minute walkthrough

1. **Table.** Open https://gray-sand-08c45ef0f.2.azurestaticapps.net/ . Six narrator models, one exam, ranked by points; the cards above the table name the Live pick, Budget pick and Most accurate.
2. **Click a narrator.** Click `gpt-5-mini` in the table to see where it fell for traps (https://gray-sand-08c45ef0f.2.azurestaticapps.net/fixtures shows the whole grid).
3. **Compare at its worst moment.** https://gray-sand-08c45ef0f.2.azurestaticapps.net/compare/fx-01/bt-001374-card?focus=gpt-5-mini : a card moment where `gpt-5-mini` named a player without citing the fact that names him. Read the verdict, the cited facts and how the other narrators handled the same moment.
4. **Use on Desk.** Click Use on Desk (or open https://gray-sand-08c45ef0f.2.azurestaticapps.net/desk?narrator=gpt-5-mini&fixture=fx-01 ). The bar reads READY until you press Run.
5. **Run live.** Pick Run live (offered for live-ready narrators). The model narrates the match as it plays; the pace control sets the match clock, and key moments always play in real time.
6. **A verdict lands.** Each claim shows CHECKING, then STANDS, AMENDED or OVERTURNED, with its evidence in the rail.
7. **See how the others called it.** From a verdict, follow the link back to Compare for that moment (`/compare/<fixture>/<beat>`).

## Testing instructions

Run locally:

```bash
make setup      # uv sync --all-packages; npm ci in apps/web
make web-dev    # http://localhost:3000 (works without the API: Table, Compare, Fixtures and the Desk's cached replays)
make api-dev    # http://localhost:8000 (needed only for Run live; needs Azure access)
```

Run the tests:

```bash
make lint typecheck test
cd apps/web && npx playwright test e2e/trials.spec.ts   # the Trials e2e spec
```

One-fixture pack smoke (needs Azure access: `az login` and model deployments in your subscription):

```bash
uv run python -m evals.trials --candidates gpt-5-mini --fixtures fx-01
```

## What to look for

- **Traps.** Each fixture plants moments a careless narrator gets wrong (a red card on the hour, a stoppage-time penalty, a lead that changes late). The Fixtures grid marks them.
- **The referee's three layers.** Code reconciles every number and name against the fact registry; a judge (`gpt-5-mini`) reads the wording; an auditor (`grok-4.7`) re-checks what stood, and the consensus verdict is the one that counts.
- **The AMENDED redline.** When a claim goes slightly beyond its facts, the referee does not drop it: Compare shows the narrator's wording with the removed words struck and the inserted ones marked.
- **NO ANSWER vs OVERTURNED.** NO ANSWER (shown as HELD) means the model gave nothing usable for that moment and scores 0. OVERTURNED means a claim was written but could not be traced to its cited facts, even if it happens to be true, and scores -3.
