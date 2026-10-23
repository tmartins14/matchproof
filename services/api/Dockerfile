# Build context is the repo root (see azure.yaml): docker build -f services/api/Dockerfile .
FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.11.23 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages ./packages
COPY services ./services
RUN uv sync --frozen --no-dev --no-editable --package matchproof-api

FROM python:3.12-slim
RUN useradd --system --uid 10001 --no-create-home app
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
# Runtime files the installed packages read through MATCHPROOF_ROOT (contracts.paths).
COPY packages/agents/config ./packages/agents/config
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 MATCHPROOF_ROOT=/app
USER app
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
