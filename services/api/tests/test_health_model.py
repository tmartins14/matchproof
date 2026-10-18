import pytest
from agents.llm_client import LlmClient, LlmError, LlmReply
from api import main
from fastapi.testclient import TestClient


class FakeClient:
    def __init__(self, result: LlmReply | LlmError) -> None:
        self.result = result

    def complete(self, prompt: str, *, max_tokens: int = 64) -> LlmReply:
        if isinstance(self.result, LlmError):
            raise self.result
        return self.result


def use_client(
    monkeypatch: pytest.MonkeyPatch, result: LlmReply | LlmError
) -> TestClient:
    monkeypatch.setattr(main, "get_llm_client", lambda: FakeClient(result))
    return TestClient(main.app)


def test_health_model_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    response = use_client(monkeypatch, LlmReply("ready", "claude-sonnet", 120)).get(
        "/health/model"
    )
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "model": "claude-sonnet",
        "reply": "ready",
        "latency_ms": 120,
    }


def test_health_model_failure_returns_class_name_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = use_client(monkeypatch, LlmError("APITimeoutError")).get("/health/model")
    assert response.status_code == 503
    assert response.json() == {"status": "error", "error": "APITimeoutError"}


def test_health_model_missing_config_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MODEL_BASE_URL", raising=False)
    monkeypatch.delenv("MODEL_DEPLOYMENT_NAME", raising=False)
    main.get_llm_client.cache_clear()
    response = TestClient(main.app).get("/health/model")
    assert response.status_code == 503
    assert response.json()["error"] == "MissingModelConfig"


def test_client_type_is_exported() -> None:
    assert LlmClient
