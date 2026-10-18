# Build prompt 02 — Azure walking skeleton (M1)

**Mode:** code. **Budget:** one sitting, about 3 hours. **Branch:** `feat/azure-skeleton`. **Depends on:** prompt 01 merged.

## Context

Read `CLAUDE.md`, `docs/ARCHITECTURE.md` (Azure services table) and `docs/adr/0002-foundry-and-agent-framework.md`. This task proves the cloud path end to end before any real features exist: a container on Azure Container Apps calls a model deployed in a Microsoft Foundry project using managed identity, and returns the answer over HTTP.

Azure service names, SDK package names and Bicep resource API versions change often. **Check current Microsoft Learn documentation for each one before using it**, and cite the pages you used in the PR. Do not rely on memory for package names or API versions.

Before writing: restate the task back in five lines or fewer, list the Azure resources you plan to create, and wait for my go.

## Seam rules

- No keys or connection strings in code, config or environment files. Managed identity in Azure; `az login` locally (`DefaultAzureCredential`).
- The model call goes through one thin client module, `packages/agents/src/agents/llm_client.py`, so the model and SDK can be swapped without touching callers.

## Parts

1. **Infra as code** under `infra/` with `azure.yaml` for the Azure Developer CLI and Bicep modules for:
   - Resource group naming with an `environmentName` parameter and a `location` parameter.
   - Log Analytics workspace and Application Insights.
   - Azure Container Registry.
   - Container Apps environment and one Container App, `api`, with a user-assigned managed identity, scale to zero, min 0 / max 2 replicas, external ingress on port 8000.
   - Storage account with one blob container, `matches`.
   - Microsoft Foundry: the AI services account and project, plus one model deployment whose name and model are parameters (`modelDeploymentName`, `modelName`, `modelVersion`).
   - Role assignments so the managed identity can call the model, read and write the blob container, and pull from the registry. Least privilege; name each role in a comment.
   - An Azure budget alert at a `budgetAmount` parameter (default 50, in the subscription currency) emailing a `budgetEmail` parameter.
2. **Container image** for `services/api`: a Dockerfile (multi-stage, non-root user, `uv` install) that `azd` builds and pushes.
3. **API endpoints:**
   - `GET /health` (unchanged).
   - `GET /health/model` calls the model once with a fixed prompt ("Reply with the single word: ready") through `llm_client.py`, with a 15 s timeout, and returns `{"status": "ok", "model": <deployment name>, "reply": <text>, "latency_ms": <int>}`. On any failure it returns HTTP 503 with the error class name, never the raw exception text.
   - OpenTelemetry tracing to Application Insights, so the model call shows as a dependency.
4. **Model choice.** Check which models are deployable in the chosen region with available quota. Prefer a Claude model in Foundry if it is available; otherwise the strongest available GPT deployment. Record the choice, region and quota seen in `docs/adr/0002-foundry-and-agent-framework.md` under a new "Decision log" heading.
5. **Docs.** `docs/DEPLOY.md`: prerequisites, `azd auth login`, `azd up`, how to find the URL, how to tear down with `azd down --purge`, expected monthly cost at idle.

## Verification signal (show the output)

1. `azd up` completes from a clean checkout.
2. `curl https://<api-url>/health/model` returns HTTP 200 with a non-empty `reply`.
3. The Application Insights transaction search shows that request with the model dependency. Include a screenshot.
4. `grep -rniE "(api[_-]?key|connectionstring|secret)" --include=*.py --include=*.bicep --include=*.yaml .` finds nothing that is a real credential.
5. `make lint typecheck test` still exits 0, and CI is green.

## Omissions list (required in the PR)

What was not verified, assumptions made, the region and quota seen, and any documentation that contradicted another page.

## Out of scope

Agents, Agent Framework workflows, the MCP server, the generator, SSE, Static Web Apps, the custom domain, Translator, Key Vault secrets (none are needed yet), Fabric.
