from functools import lru_cache
from importlib.metadata import version

from agents.llm_client import LlmClient, LlmError, from_env
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from api.telemetry import configure_telemetry

MODEL_CHECK_PROMPT = "Reply with the single word: ready"
MODEL_CHECK_TIMEOUT_S = 15.0

configure_telemetry()

app = FastAPI(title="Matchproof API")
FastAPIInstrumentor.instrument_app(app)


@lru_cache(maxsize=1)
def get_llm_client() -> LlmClient:
    return from_env()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": version("matchproof-api")}


@app.get("/health/model", response_model=None)
def health_model() -> dict[str, str | int] | JSONResponse:
    try:
        reply = get_llm_client().complete(MODEL_CHECK_PROMPT)
    except LlmError as exc:
        return JSONResponse(
            status_code=503, content={"status": "error", "error": exc.cause_name}
        )
    return {
        "status": "ok",
        "model": reply.model,
        "reply": reply.text,
        "latency_ms": reply.latency_ms,
    }
