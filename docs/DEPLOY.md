# Deploying Matchproof to Azure

The walking skeleton is one Container App (`api`) that calls a `gpt-5-mini` deployment in a Microsoft Foundry project with a user-assigned managed identity. Everything is created by `azd up` from `infra/`.

## Prerequisites

- Azure CLI (`az`), Azure Developer CLI (`azd` 1.36 or later) and Docker.
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

Optional overrides: `MODEL_DEPLOYMENT_NAME` (default `gpt-5-mini`), `MODEL_NAME` (`gpt-5-mini`), `MODEL_VERSION` (`2025-08-07`), `MODEL_CAPACITY` (`50`, thousands of tokens per minute), `BUDGET_AMOUNT` (`50`, in the subscription currency).

`azd up` builds the image in Azure Container Registry (`remoteBuild`), so no local architecture match is needed.

## Find the URL

```bash
azd env get-value API_URL
curl "$(azd env get-value API_URL)/health"
curl "$(azd env get-value API_URL)/health/model"
```

The first request after idle is slow while the app scales up from zero.

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
