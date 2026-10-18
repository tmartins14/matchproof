# Build prompt 01 — Scaffold, schema codegen and CI

**Mode:** code. **Budget:** one sitting, about 2 hours. **Branch:** `feat/scaffold-ci`.

## Context

Matchproof is a hackathon entry (deadline Oct 27): an agent system that generates a synthetic football match, streams it live, narrates it and proves every claim against the event log. Read `CLAUDE.md`, `docs/SPEC.md`, `docs/ARCHITECTURE.md` and `docs/adr/` before writing anything. The JSON Schemas in `schemas/` are final for this task and are the contract.

This task creates the empty, working monorepo that every later task builds into. No football logic, no Azure, no agents yet.

Before writing: restate the task and its constraints back in five lines or fewer, then wait for my go.

## Seam rules

- Python computes; agents narrate; the browser renders.
- Schemas are the contract. Python models and TypeScript types are generated from `schemas/`, never hand-written.

## Parts

1. **Python workspace** with `uv`, Python 3.12, one workspace and four packages under `packages/`: `sim`, `intel`, `agents`, `mcp_match`, plus `services/api`. Each package: `pyproject.toml`, `src/<name>/__init__.py`, `tests/test_smoke.py`. Shared dev dependencies at the root: `ruff`, `mypy`, `pytest`, `jsonschema`, `referencing`, `datamodel-code-generator`.
2. **Schema codegen.**
   - Script `scripts/gen_models.py` generates Pydantic v2 models from every `schemas/*.schema.json` into `packages/contracts/src/contracts/models.py` (add `contracts` as a fifth package that the others depend on).
   - Script `scripts/gen_types.mjs` (or an npm script using `json-schema-to-typescript`) generates `apps/web/src/contracts/types.ts`.
   - Script `scripts/check_contracts.py` meta-validates every schema and validates `schemas/examples/*.json` against `claim_graph.schema.json`, resolving `$ref`s with a `referencing.Registry` keyed by each schema's `$id`.
   - A test fails if the generated files are out of date with the schemas (regenerate to a temp path and diff).
3. **Web app** at `apps/web`: Next.js (App Router), TypeScript strict, ESLint. One page at `/` that renders "Matchproof" and imports one generated type to prove the wiring. A `src/theme/tokens.ts` with the two themes, `broadcast` and `editorial`, copied from the `tokens()` function in `docs/prototype/Main.dc.html` (same keys and values). No other UI.
4. **API stub** at `services/api`: FastAPI app with `GET /health` returning `{"status": "ok", "version": <package version>}`. A pytest test for it.
5. **Makefile** (or `justfile`) with: `setup`, `gen`, `lint`, `typecheck`, `test`, `web-dev`, `api-dev`, `check-contracts`.
6. **CI** at `.github/workflows/ci.yml`, on pull requests and pushes to `main`: install with `uv` and `npm ci`; run `make check-contracts lint typecheck test`; build the web app. Cache `uv` and npm.
7. **Repo hygiene:** `.gitignore` (Python, Node, `.env*`, `.azure/`), `LICENSE` (MIT, Tyler Martins, 2026), `.editorconfig`, and fill in the `## Commands` section of `CLAUDE.md` in a **separate one-line commit**.

## Conventions

- Python: snake_case modules and functions, `ruff` defaults plus `I` (imports) and `UP`, `mypy --strict` on `src/`.
- TypeScript and JavaScript: camelCase method and function names. No default exports except Next.js pages.
- No real Premier League names or data anywhere.

## Verification signal (show the output)

1. `make setup gen check-contracts lint typecheck test` exits 0, run from a clean clone.
2. `cd apps/web && npm run build` exits 0.
3. Edit any schema description locally, run `make test`, show the stale-codegen test failing, then revert.
4. CI is green on the PR.

## Omissions list (required in the PR)

List what you did not verify and every assumption you made, for example package versions chosen and why.

## Out of scope

Azure, infra, Bicep, Docker, agents, the generator, any football logic, any UI beyond the one page, authentication, deployment.
