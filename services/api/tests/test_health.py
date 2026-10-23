import pytest
from agents.budget import budget
from api.main import app
from fastapi.testclient import TestClient


def test_health() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}


def test_health_budget_reports_tokens_against_the_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DAILY_TOKEN_CAP", "5000")
    budget._used.clear()
    budget._split.clear()  # other tests in this worker leave their own usage behind
    budget.add(
        "narrator", 120, deployment="gpt-5-mini", input_tokens=100, output_tokens=20
    )
    budget.add("auditor", 30)
    try:
        body = TestClient(app).get("/health/budget").json()
    finally:
        budget._used.clear()
        budget._split.clear()
    assert body["cap"] == 5000 and body["used"] == 150
    assert body["by_role"] == {"narrator": 120, "auditor": 30}
    assert body["narration_paused"] is False and body["auditing_stopped"] is False
    assert body["usage"]["narrator"] == {
        "deployment": "gpt-5-mini",
        "input": 100,
        "output": 20,
    }
    assert body["cost"] == "prices not set"
