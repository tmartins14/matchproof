# Build prompt 13 — Deploy the live desk to Azure (M3)

**Mode:** code. **Budget:** about 2 to 2.5 hours. **Branch:** `feat/deploy-web`. **Depends on:** PR 29 merged, with self-hosted fonts. **Lands before:** prompt 14 (cached replay and pre-generated matches).

## Context

Read:

- `CLAUDE.md`
- `docs/DEPLOY.md`
- `docs/ARCHITECTURE.md` (Azure services)
- `docs/PLAN.md` (compliance rows 4.3, 4.8 and 6.1)
- `azure.yaml`
- `infra/main.bicep`, `infra/main.parameters.json` and `infra/modules/*.bicep`, especially `containerapp.bicep` (`minReplicas: 0`, env vars)
- `apps/web/next.config.ts`, `src/app/page.tsx` and `src/desk/reviewParams.ts`
- `services/api/src/api/main.py` (the CORS middleware from prompt 12)

The API runs on Container Apps. The desk has only run on `localhost`. This task puts the desk on **Azure Static Web Apps**, connects it to the API with production CORS, and makes the deployed pair fit for judging: no login, no cold-start stall on the first click, and checked every 5 minutes until Nov 10 (rule 4.8). The browser calls the API directly for REST and SSE. It is **not** proxied through Static Web Apps, so streams aren't buffered.

Azure service names, Bicep API versions, `azd` host settings and Static Web Apps behaviour change often. **Check current Microsoft Learn documentation for each one before using it**, and cite the pages in the PR. Don't rely on memory.

Before writing, restate the task in ten lines or fewer. Include how `NEXT_PUBLIC_API_URL` reaches the build, how `WEB_ORIGINS` reaches the API, what replaces the server-side `searchParams` read for static export, and the monthly cost of `minReplicas: 1` (from the pricing page, idle rate included). Wait for my go.

## Rules

- No keys or tokens in the repo. Static Web Apps deploys through `azd` with the signed-in identity. If any token is unavoidable, it lives in `azd env` only and is named in the PR.
- The desk is a static export. Nothing in `apps/web` may need a Node server at runtime.
- One `azd up` from a clean environment brings up both services. The PR proves it.

## Parts

1. **Static export.**
   - Set `output: "export"` in `next.config.ts`.
   - `page.tsx` currently reads `searchParams` on the server, which static export can't do. Move the review-parameter parsing (`source`, `lang`, `mode`, `beat`, `claim`, `setup`, `stamp`) into a client component using `useSearchParams` inside a `Suspense` boundary. Live stays the default, and `?source=fixture` still renders the fixture desk.
   - Do the same for `/review/key-moments` and `/review/stat-cards`, or exclude them from the export if they're only test aids. Say which.
   - `npm run build` must produce `apps/web/out/` with no dynamic routes. Show the route table.
   - Playwright and `npm run shots` keep working against the exported build (`npx serve out` or equivalent). Update the Playwright `webServer`.
2. **Infra: Static Web App.**
   - Add `infra/modules/staticwebapp.bicep`: Free tier, in a region that supports Static Web Apps (`eastus2` matches the default `AZURE_LOCATION`).
   - Output its default hostname as `WEB_URL`.
   - Wire it into `main.bicep`.
3. **azd service.**
   - Add a `web` service to `azure.yaml`: `project: ./apps/web`, `host: staticwebapp`, `dist: out`, `language: js`.
   - The build must see `NEXT_PUBLIC_API_URL` = the API's URL. Use an azd hook (for example `prepackage` on `web`) that writes `apps/web/.env.production.local` from `azd env get-value API_URL`. Keep that file out of git.
   - A build without the variable fails loudly; it never falls back to `localhost` in production. Keep the `localhost` default for `next dev` only.
4. **Production CORS.**
   - Add a Bicep parameter `webOrigins` (string, comma-separated) to `containerapp.bicep`, set as the `WEB_ORIGINS` env var.
   - `main.bicep` passes the Static Web App's `https://` hostname, plus `CUSTOM_WEB_ORIGIN` from `azd env` when it's set (for `https://matchproof.tylermartins.com`).
   - Keep `http://localhost:3000` out of production.
   - Test: a preflight from the Static Web Apps origin is allowed, and one from `https://example.com` is refused (run in the smoke script, Part 8).
5. **No cold-start stall during judging.**
   - Add a Bicep parameter `apiMinReplicas` (default `1`), used for `minReplicas`.
   - Document the cost in `docs/DEPLOY.md` with the idle-rate figure from the pricing page. Also document how to set it back to `0` after Nov 10 (`azd env set API_MIN_REPLICAS 0`, then `azd provision`).
   - Raise the `BUDGET_AMOUNT` default if the new monthly estimate exceeds 80% of it, and say so in the PR.
6. **SSE through Container Apps ingress.**
   - Confirm in the docs that ingress doesn't buffer `text/event-stream`, and find its idle timeout. The 15 s heartbeat must be under it. Cite both.
   - If anything needs configuring (ingress transport, timeouts), do it in Bicep.
7. **Custom domain (two steps, documented).**
   - Bicep can't finish domain validation alone. Write `docs/DEPLOY.md` § Custom domain:
     - Tyler adds a CNAME `matchproof` → the Static Web Apps default hostname at his DNS provider;
     - then runs one `az staticwebapp hostname set …` command (give it exactly), then `azd env set CUSTOM_WEB_ORIGIN https://matchproof.tylermartins.com` and `azd provision`.
   - Add a script `scripts/check_domain.sh` that reports whether the CNAME resolves and the hostname is validated.
   - Don't block the PR on the domain. The default hostname is the fallback submission URL.
8. **Smoke script and uptime.**
   - `scripts/smoke_prod.sh` reads `WEB_URL` and `API_URL` from `azd env`, or takes them as arguments, and checks:
     1. the web root returns 200 with the desk's HTML;
     2. `API_URL/health` returns 200 with `agents` ready;
     3. the CORS preflight from the web origin is allowed and from `https://example.com` refused;
     4. `POST /matches/random`, then `GET /matches/{id}/stream?speed=6` delivers a `status` and at least one `event` within 30 s, then closes;
     5. `GET /matches` returns 200.

     It exits non-zero on any failure, printing which check failed.
   - Add Application Insights **standard availability tests**, in Bicep, for the web root and `API_URL/health`, every 5 minutes from 3 regions, with an alert rule emailing `BUDGET_EMAIL` on 2 consecutive failures.
9. **Docs.**
   - `docs/DEPLOY.md`: the web service, the API URL hook, CORS, min replicas and cost, the custom domain, the smoke script, availability tests, and the "after Nov 10" teardown steps.
   - README `## Status`: one paragraph.
   - In `docs/PLAN.md`, tick the compliance rows this satisfies (4.8 Testing, and 6.1 Static Web Apps), each with the evidence.

## Verification signal (show the output)

1. `make check-contracts lint typecheck test`, and `npm run build` with the network blocked, both exit 0. CI is green.
2. The exported route table, with no `ƒ` routes.
3. **Deploy** (Tyler runs it if CC can't authenticate; say which): `azd up` from a fresh `azd env`, then `scripts/smoke_prod.sh`, with all checks passing. Paste both outputs.
4. Screenshots of the deployed desk at the Static Web Apps URL:
   - pre-match;
   - one live match at 6× mid-stream;
   - full time.

   This is M3: kick off a match on the live URL and watch claims get checked.
5. The availability test results, or the portal view of them, after the first runs.

## Omissions list (required in the PR)

- Every doc page that disagreed with another, or with memory.
- Anything verified only locally.
- The custom-domain state at the time of the PR.
- The real monthly cost estimate.

## Out of scope

- Cached replay, the Watch cached replay button, and pre-generated matches (prompt 14).
- The Localizer, the overlay route, movement v2.
- Authentication: the desk is public with no login, by rule 4.8.
