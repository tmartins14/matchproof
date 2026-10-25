# Deploying Matchproof to Azure

The deployment is two services: the desk, a static export on Azure Static Web Apps (`web`), and one Container App (`api`) that calls a `gpt-5-mini` deployment in a Microsoft Foundry project with a user-assigned managed identity. Everything is created by `azd up` from `infra/`. The browser calls the API directly for REST and SSE; Static Web Apps does not proxy it.

## Prerequisites

- Azure CLI (`az`), Azure Developer CLI (`azd` 1.36 or later), Docker and Node 22 (the desk is built on your machine, not in Azure).
- An Azure subscription where you can create resources and role assignments (Owner, or Contributor plus User Access Administrator), and has quota for the model you deploy (see `docs/adr/0002-foundry-and-agent-framework.md`, Decision log).
- Resource providers registered once per subscription: `Microsoft.App`, `Microsoft.CognitiveServices`, `Microsoft.ContainerRegistry`, `Microsoft.OperationalInsights`, `Microsoft.Insights`, `Microsoft.Storage`, `Microsoft.Consumption`.

## Deploy

```bash
az login
azd auth login
azd env new matchproof-dev
azd env set AZURE_SUBSCRIPTION_ID <subscription-id>
azd env set AZURE_LOCATION eastus2
azd env set BUDGET_EMAIL <you@example.com>
azd up
```

Optional overrides: `MODEL_DEPLOYMENT_NAME` (default `gpt-5-mini`), `MODEL_NAME` (`gpt-5-mini`), `MODEL_VERSION` (`2025-08-07`), `MODEL_CAPACITY` (`50`, thousands of tokens per minute), `BUDGET_AMOUNT` (`50`, in the subscription currency), `CUSTOM_WEB_ORIGIN` (empty), `API_MIN_REPLICAS` (`1`).

`azd up` builds the image in Azure Container Registry (`remoteBuild`), so no local architecture match is needed.

## Find the URL

```bash
azd env get-value WEB_URL
azd env get-value API_URL
curl "$(azd env get-value API_URL)/health"
curl "$(azd env get-value API_URL)/health/model"
```

With `API_MIN_REPLICAS=0` the first request after idle is slow while the app scales up from zero; the default of 1 keeps a replica warm (see Min replicas and cost).

## Container size and streams

The API container has 1 vCPU and 2 GiB (`infra/modules/containerapp.bicep`). Each live stream runs a generator, fact engine and beat detector on a worker thread, so one replica serves at most `MAX_LIVE_STREAMS = 3` streams at once. A fourth gets HTTP 503 with `Retry-After: 30` and the body `{"fallback": "cached"}`; the cached replay that answers it comes Sunday.

## Connect with an MCP client

The read-only match-data server is at `<API_URL>/mcp` (streamable HTTP, no key, 60 requests per minute per client). Start a match first, then list its beats:

```bash
API_URL="$(azd env get-value API_URL)"
curl -s -X POST "$API_URL/matches" -H 'Content-Type: application/json' -d '{"story": "red_card_flip", "seed": 3}'
npx @modelcontextprotocol/inspector --cli "$API_URL/mcp" --transport http --method tools/list
npx @modelcontextprotocol/inspector --cli "$API_URL/mcp" --transport http --method tools/call --tool-name list_beats --tool-arg match_id=<match_id>
```

A match shows up in the server once its stream has started (`GET /matches/{match_id}/stream`).

## Run locally

```bash
az login
export MODEL_BASE_URL="$(azd env get-value MODEL_BASE_URL)"
export MODEL_DEPLOYMENT_NAME="$(azd env get-value MODEL_DEPLOYMENT_NAME)"
make api-dev
```

Your own user needs the `Cognitive Services OpenAI User` role on the Foundry account to call the model locally.

## Find a match's trace

Every match run is one OpenTelemetry trace. A claim's `checker.trace_id` is its trace id, and its `verdict` message carries the beat's span id. Locally, `make api-dev` prints spans to the console (`MATCHPROOF_TRACE_CONSOLE=1`); in Azure they go to Application Insights. In the Logs blade of the Application Insights resource, with the trace id from a claim:

```kusto
union dependencies, requests, traces
| where operation_Id == "<trace_id>"
| project timestamp, itemType, name, duration, id, operation_ParentId, customDimensions
| order by timestamp asc
```

The `match` span is the root. Each `beat` span has `producer`, `narrate`, `check` (with `reconcile`, `lint` and `judge`), `retry` and `put_claims` children. An `audit` span sits under the match and links to the beat span it audits.

## List archived matches

Finished matches are saved to the `matches` container of the storage account (`MATCH_ARCHIVE=blob` is set on the container app). A match is complete when its `manifest.json` is there.

```bash
ACCOUNT="$(azd env get-value AZURE_STORAGE_ACCOUNT)"
az storage blob list --account-name "$ACCOUNT" --container-name matches --auth-mode login \
  --query "[?ends_with(name, '/manifest.json')].{match:name, size:properties.contentLength, modified:properties.lastModified}" -o table
az storage blob list --account-name "$ACCOUNT" --container-name matches --prefix "<match_id>/" --auth-mode login -o table
```

Your own user needs `Storage Blob Data Reader` on the container for `--auth-mode login`. `GET /matches` on the API lists the same matches with their scores and claim counts. Locally the files are under `data/archive/`.

## Tear down

```bash
azd down --purge
```

`--purge` removes the soft-deleted Foundry account, which otherwise keeps its token quota reserved for up to 48 hours.

## Expected cost at idle

Estimates, not taken from a pricing page: the container app scales to zero and the model deployment is billed per token, so idle cost is mostly Azure Container Registry Basic (about US$5 per month) plus negligible storage, Log Analytics and Application Insights ingestion. Model use is billed per token on top. The budget alert emails at 80% and 100% of actual spend and 100% of forecast spend for the resource group.

## The web service

`azure.yaml` has a `web` service: `apps/web`, `host: staticwebapp`, `dist: out`. `infra/modules/staticwebapp.bicep` creates a Free-tier Static Web App (`Microsoft.Web/staticSites@2025-03-01`) tagged `azd-service-name: web`, in `AZURE_LOCATION` (Static Web Apps supports `eastus2`, the default; a location it does not support fails at provision). It is not linked to a repository, so `azd deploy web` uploads `apps/web/out` with the signed-in identity and no token is stored.

The desk is a static export (`output: "export"`), so nothing in `apps/web` needs a Node server. The review parameters (`source`, `lang`, `mode`, `beat`, `claim`, `setup`, `stamp`, `labels`) are read in the browser with `useSearchParams` inside a `Suspense` boundary. The two `/review/*` pages are kept in the export because `e2e/review.spec.ts` tests them; they read `lang` the same way.

### How the API URL reaches the build

The browser bundle has the API URL baked in at build time. A `prepackage` hook on `web` writes `apps/web/.env.production.local` (git-ignored through `.env*`) with `NEXT_PUBLIC_API_URL=<API_URL from azd env>`. `next.config.ts` throws if a production build has no `NEXT_PUBLIC_API_URL`, so a build never falls back to `localhost`; only `next dev` defaults to `http://localhost:8000`. CI sets a placeholder (`https://api.invalid`) for its build check only. `npm run shots` sets `http://localhost:8000` for its local build.

### CORS

`containerapp.bicep` takes `webOrigins` (comma-separated) and sets it as `WEB_ORIGINS`. `main.bicep` passes `https://<Static Web App hostname>` plus `CUSTOM_WEB_ORIGIN` when set. `http://localhost:3000` is not in production. `scripts/smoke_prod.sh` checks that a preflight from the web origin is allowed and one from `https://example.com` is refused.

## Min replicas and cost

`apiMinReplicas` (`azd env set API_MIN_REPLICAS`) defaults to `1` so the first click in judging does not wait for a cold start.

Rates, from the Azure Retail Prices API for `eastus2` (the pricing page itself renders its rates as placeholders): idle usage is $0.000003 per vCPU-second and $0.000003 per GiB-second; active usage is $0.000024 per vCPU-second and $0.000003 per GiB-second. For 1 vCPU and 2 GiB over a 30-day month (2,592,000 s) fully idle:

- vCPU: 2,592,000 × 0.000003 = $7.78
- memory: 2 × 2,592,000 × 0.000003 = $15.55
- about **$23.3 a month** before the free grants (180,000 vCPU-seconds and 360,000 GiB-seconds per subscription per month), about $21.7 after them.

A replica is idle only while it serves no request, uses under 0.01 vCPU and receives under 1,000 bytes per second; streams and matches bill at the active rate, so the real figure is a little higher. Requests are $0.40 per million after the first 2 million. Static Web Apps Free tier and Application Insights availability tests are separate (tests are billed per Azure Monitor pricing). The $50 `BUDGET_AMOUNT` stays: the idle estimate is under 80% of it ($40).

After Nov 10, to go back to scale-to-zero:

```bash
azd env set API_MIN_REPLICAS 0
azd provision
```

## SSE through Container Apps ingress

Microsoft Learn's ingress overview (`learn.microsoft.com/azure/container-apps/ingress-overview`) states the HTTP request time-out is 240 seconds. The API sends an SSE comment line after every 15 s of silence (`HEARTBEAT_S` in `services/api/src/api/live.py`), well under that. The same page says nothing about whether ingress buffers `text/event-stream`, so that is not confirmed by the docs; `scripts/smoke_prod.sh` check 4 proves a stream delivers its first events through the deployed ingress. No ingress setting needed changing, so `containerapp.bicep` keeps `transport: 'auto'`.

## Custom domain

Bicep cannot finish domain validation alone, so this is two steps by hand. The default `*.azurestaticapps.net` hostname is the fallback submission URL.

1. At your DNS provider add a CNAME: `matchproof` → the value of `azd env get-value WEB_URL` without `https://`.
2. Once it resolves, validate it on the Static Web App, then tell the API to allow the origin:

```bash
az staticwebapp hostname set -n "$(az staticwebapp list -g "$(azd env get-value AZURE_RESOURCE_GROUP)" --query '[0].name' -o tsv)" \
  -g "$(azd env get-value AZURE_RESOURCE_GROUP)" --hostname matchproof.tylermartins.com
azd env set CUSTOM_WEB_ORIGIN https://matchproof.tylermartins.com
azd provision
```

`scripts/check_domain.sh` reports whether the CNAME resolves and the hostname is validated (`Ready`).

## Smoke test

```bash
scripts/smoke_prod.sh                # reads WEB_URL and API_URL from azd env
scripts/smoke_prod.sh <WEB_URL> <API_URL>
```

It checks, and exits non-zero naming the failing one: (1) the web root is 200 with the desk's HTML, (2) `/health` is 200 with `agents` ready, (3) CORS is allowed from the web origin and refused from `https://example.com`, (4) `POST /matches/random` then `GET /matches/{id}/stream?speed=6` delivers a `status` and an `event` within 30 s, (5) `GET /matches` is 200. It starts one real match, so it costs a few model calls when agents are on.

## Availability tests

`infra/modules/availability.bicep` creates two Application Insights standard tests (`Microsoft.Insights/webtests@2022-06-15`), one for the web root and one for `<API_URL>/health`, every 5 minutes from three locations (East US, West Europe, Japan East), with retries on. A metric alert per test emails `BUDGET_EMAIL` through an action group when two of the three locations fail within a 10-minute window (two runs). Learn recommends at least five locations; three is what the plan asks for. Results: Application Insights → Investigate → Availability.

## After Nov 10

```bash
azd env set API_MIN_REPLICAS 0 && azd provision   # scale the API back to zero
azd down --purge                                  # or remove everything
```

Disable the availability alert rules first if you keep the app, or the 5-minute tests keep waking the API.
