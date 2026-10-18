.PHONY: setup gen lint typecheck test web-dev api-dev check-contracts

setup:
	uv sync --all-packages
	cd apps/web && npm ci

gen:
	uv run python scripts/gen_models.py
	node scripts/gen_types.mjs

check-contracts:
	uv run python scripts/check_contracts.py

lint:
	uv run ruff check .
	uv run ruff format --check .
	cd apps/web && npm run lint

typecheck:
	uv run mypy packages/*/src services/api/src scripts
	cd apps/web && npm run typecheck

test:
	uv run pytest

web-dev:
	cd apps/web && npm run dev

api-dev:
	uv run uvicorn api.main:app --reload --app-dir services/api/src
