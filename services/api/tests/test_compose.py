from collections.abc import Iterator
from typing import Any

import pytest
from agents.budget import MeteredClient, budget
from api import main
from api.matchdata import RateLimiter
from fastapi.testclient import TestClient
from sim.brief import random_brief

REPLY: dict[str, Any] = {
    "home": {"formation": "4-3-3", "press": 0.9, "directness": 0.4, "line_height": 0.8},
    "away": {"formation": "4-4-2", "press": 0.1, "directness": 0.9, "line_height": 0.1},
    "storyline": "custom",
    "moments": [
        {"kind": "red_card", "side": "away", "minute_from": 38, "minute_to": 45}
    ],
}


class Chat:
    """Replies the same answer every time, so the endpoint can be called repeatedly."""

    deployment = "fake"
    response_format = "none"

    def __init__(self, reply: dict[str, Any]) -> None:
        self.reply = reply
        self.calls = 0

    def complete(self, prompt: str, **_: Any) -> Any:
        import json

        from agents.llm_client import LlmReply

        self.calls += 1
        return LlmReply(json.dumps(self.reply), "fake", 1, 100, 50)


@pytest.fixture
def chat(monkeypatch: pytest.MonkeyPatch) -> Iterator[Chat]:
    fake = Chat(REPLY)
    monkeypatch.setattr(
        main, "make_composer_client", lambda: MeteredClient(fake, "composer")
    )
    monkeypatch.setattr(
        main, "_compose_limiter", RateLimiter(main.COMPOSE_RPM_PER_CLIENT)
    )
    budget._used.clear()
    budget._split.clear()
    yield fake
    budget._used.clear()
    budget._split.clear()


def test_compose_returns_brief_text_and_warnings(chat: Chat) -> None:
    body = (
        TestClient(main.app)
        .post("/compose", json={"text": "Ashford lose a man"})
        .json()
    )
    assert body["warnings"] == []
    assert body["brief"]["storyline"]["id"] == "custom"
    assert body["brief"]["planted_beats"][0]["kind"] == "red_card"
    assert "Custom: Ashford Vale red card 38–45′" in body["brief_text"]
    assert body["brief_text"] == body["brief"]["brief_text"]


def test_the_seventh_call_in_a_minute_is_429(chat: Chat) -> None:
    client = TestClient(main.app)
    codes = [client.post("/compose", json={"text": "x"}).status_code for _ in range(7)]
    assert codes == [200] * 6 + [429]
    assert chat.calls == 6


def test_compose_counts_toward_the_daily_cap(
    chat: Chat, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = TestClient(main.app)
    client.post("/compose", json={"text": "x"})
    assert budget.snapshot()["by_role"] == {"composer": 150}
    monkeypatch.setenv("DAILY_TOKEN_CAP", "100")
    response = client.post("/compose", json={"text": "x"})
    assert response.status_code == 503 and "DailyTokenCap" in response.json()["detail"]


@pytest.mark.parametrize(
    "body", [{}, {"text": "  "}, {"text": "a" * 601}, {"text": "x", "seed": -1}]
)
def test_compose_rejects_bad_requests(chat: Chat, body: dict[str, Any]) -> None:
    assert TestClient(main.app).post("/compose", json=body).status_code == 422
    assert chat.calls == 0


def test_post_matches_accepts_a_valid_custom_brief_and_422s_an_invalid_one() -> None:
    client = TestClient(main.app)
    brief = random_brief(4).model_dump(mode="json", exclude_none=True)
    assert client.post("/matches", json=brief).status_code == 200

    brief["planted_beats"] = [
        {
            "id": "pb-01",
            "kind": "red_card",
            "side": "away",
            "minute_from": 10,
            "minute_to": 15,
        },
        {
            "id": "pb-02",
            "kind": "red_card",
            "side": "away",
            "minute_from": 60,
            "minute_to": 65,
        },
    ]
    brief["storyline"] = {"id": "custom", "text": "Custom: two reds"}
    response = client.post("/matches", json=brief)
    assert response.status_code == 422
    assert response.json()["detail"] == [
        "There can be at most one red card per side; away has 2."
    ]


def test_post_matches_random_is_repeatable_and_playable() -> None:
    client = TestClient(main.app)
    a = client.post("/matches/random", json={"seed": 7}).json()
    b = client.post("/matches/random", json={"seed": 7}).json()
    assert a == b and a["brief"] == random_brief(7).model_dump(
        mode="json", exclude_none=True
    ) | {"match_id": a["match_id"]}
    assert client.post("/matches/random", json={"seed": -1}).status_code == 422
    assert client.post("/matches/random").status_code == 200
