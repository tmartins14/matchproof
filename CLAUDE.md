# CLAUDE.md — Matchproof

Matchproof: an agent system that composes a synthetic football match, streams it live, narrates it, and proves every claim against the event log. Hackathon deadline: Tue Oct 27, 2026, 9 PM ET (internal).

## Seam rules (non-negotiable)

1. **Python computes.** All extraction, statistics, positions, beat detection and number reconciliation are deterministic Python.
2. **Agents orchestrate and narrate.** LLM output never produces a number that is not already a fact. The Narrator receives a fact bundle, never raw events.
3. **The browser renders.** The web app draws JSON it is given. It never computes football statistics.
4. **Every published claim maps to fact IDs, and every fact maps to source IDs.** A claim without that chain is blocked, not shipped.
5. **Schemas are the contract.** `schemas/*.schema.json` is the source of truth. Change a schema, then regenerate Pydantic models and TypeScript types in the same PR.
6. **Update README.md daily** After each day's worth of work, update `README.md` under ## Status

## Repo layout

```
schemas/            JSON Schema contracts
packages/sim/       generator, tactics, positions, calibration targets
packages/intel/     extractors, fact registry, beat detector, reconciler
packages/agents/    composer, producer, narrator, checker, localizer, workflow
packages/mcp_match/ MCP server over the match store
services/api/       FastAPI: SSE stream, compose, graphs
apps/web/           Next.js live desk (viz/ holds pitch and chart components)
evals/              golden matches, adversarial claims, runner
infra/              azure.yaml + Bicep
docs/               SPEC, ARCHITECTURE, adr/, prototype/, compliance/
prompts/            build prompts, one per task
voice/              voice rules and Narrator examples
```

## Docs map

- What and why: `docs/SPEC.md`. How: `docs/ARCHITECTURE.md`. Why a decision: `docs/adr/`. When: `docs/PLAN.md`.
- If they disagree, ADRs and ARCHITECTURE win on design and PLAN wins on schedule. Flag the conflict in the PR.
- UI tasks only: open `docs/prototype/prototype.html` in a browser to see the behaviour; read `docs/prototype/Main.dc.html` for logic, copy and theme tokens.

## Conventions

- Python 3.12, `uv` for environments, `ruff` + `mypy --strict`, `pytest`. snake_case module and function names.
- TypeScript strict. JavaScript and TypeScript method names in camelCase (e.g. `setPieceCornerKick`), never snake_case.
- Pitch coordinates: 120 × 80, absolute. The home team attacks toward x = 120 in both halves. See ADR 0007.
- IDs: events `ev-000123`, windows `win-NN`, aggregates `agg-<name>`, facts `fx-…`, beats `bt-…`, claims `cl-…`, momentum buckets `min-NN`.
- Product text (narration and UI copy) follows `docs/VOICE.md`; `voice/banned.yaml` is enforced in CI.
- Fictional clubs and players only. No real Premier League names, crests, marks or data in code, fixtures or UI.
- No secrets in code or config. Azure access uses managed identity; local development uses `az login`.
- Model deployments and prompts are config files under version control. A prompt change re-runs the evals.

## How work ships

- One task, one branch, one PR. Never commit to `main`.
- Every PR description has three parts: summary, verification evidence (the commands run and their output, screenshots for UI), and an omissions list (what was not verified, and assumptions made).
- UI PRs include a screenshot of the changed screen in both themes.
- Changes to this file go in their own one-line commit, never folded into a feature PR.
- If a correction fails twice, stop and say so. Do not keep patching.

## Commands

```
make setup            # uv sync --all-packages; npm ci in apps/web
make gen              # regenerate Pydantic models and TS types from schemas/
make check-contracts  # meta-validate schemas, validate examples
make lint typecheck test
make web-dev          # Next.js on :3000
make api-dev          # FastAPI on :8000
```

Never hand-edit `packages/contracts/src/contracts/models.py` or `apps/web/src/contracts/types.ts`; run `make gen`.
