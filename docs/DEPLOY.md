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

## Run locally

```bash
az login
export MODEL_BASE_URL="$(azd env get-value MODEL_BASE_URL)"
export MODEL_DEPLOYMENT_NAME="$(azd env get-value MODEL_DEPLOYMENT_NAME)"
make api-dev
```

Your own user needs the `Cognitive Services OpenAI User` role on the Foundry account to call the model locally.

## Tear down

```bash
azd down --purge
```

`--purge` removes the soft-deleted Foundry account, which otherwise keeps its token quota reserved for up to 48 hours.

## Expected cost at idle

Estimates, not taken from a pricing page: the container app scales to zero and the model deployment is billed per token, so idle cost is mostly Azure Container Registry Basic (about US$5 per month) plus negligible storage, Log Analytics and Application Insights ingestion. Model use is billed per token on top. The budget alert emails at 80% and 100% of actual spend and 100% of forecast spend for the resource group.
