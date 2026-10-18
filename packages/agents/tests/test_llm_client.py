from types import SimpleNamespace
from typing import Any

import pytest
from agents.llm_client import LlmClient, LlmError, from_env
from anthropic import APITimeoutError


class FakeMessages:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="ready")],
            usage=SimpleNamespace(input_tokens=5, output_tokens=1),
        )


def make_client(messages: FakeMessages) -> LlmClient:
    fake: Any = SimpleNamespace(messages=messages)
    return LlmClient(
        "https://example.services.ai.azure.com/anthropic", "dep", client=fake
    )


def test_complete_returns_text_and_deployment() -> None:
    messages = FakeMessages()
    reply = make_client(messages).complete("hi")
    assert (reply.text, reply.model) == ("ready", "dep")
    assert messages.calls[0]["model"] == "dep"


def test_failure_becomes_llm_error_with_class_name() -> None:
    import httpx2

    error = APITimeoutError(request=httpx2.Request("POST", "https://example.invalid"))
    with pytest.raises(LlmError) as info:
        make_client(FakeMessages(error)).complete("hi")
    assert info.value.cause_name == "APITimeoutError"


def test_from_env_requires_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MODEL_BASE_URL", raising=False)
    monkeypatch.delenv("MODEL_DEPLOYMENT_NAME", raising=False)
    with pytest.raises(LlmError):
        from_env()
