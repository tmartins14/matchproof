# Matchproof: guide for judges

Live site: https://gray-sand-08c45ef0f.2.azurestaticapps.net/

## 2-minute walkthrough (1:59)

1. **Table** (0:00): https://gray-sand-08c45ef0f.2.azurestaticapps.net/ . Six narrators, one exam, ranked by points.
2. **Click a narrator** (0:15): click `gpt-5-mini` to see where it fell for traps (https://gray-sand-08c45ef0f.2.azurestaticapps.net/fixtures shows the whole grid).
3. **Compare at its worst moment** (0:30): https://gray-sand-08c45ef0f.2.azurestaticapps.net/compare/fx-01/bt-001374-card?focus=gpt-5-mini . It named a player without citing the fact that names him; the other narrators' calls sit alongside.
4. **Use on Desk** (0:55): https://gray-sand-08c45ef0f.2.azurestaticapps.net/desk?narrator=gpt-5-mini&fixture=fx-01 . The bar reads READY until you press Run.
5. **Run live** (1:05): press Run live. Key moments always play in real time.
6. **A verdict lands** (1:20): CHECKING, then STANDS, AMENDED or OVERTURNED, with the evidence in the rail.
7. **See how the others called it** (1:40): follow the link back to Compare for that moment (https://gray-sand-08c45ef0f.2.azurestaticapps.net/compare/fx-01/bt-001374-card). End at 1:59.

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
