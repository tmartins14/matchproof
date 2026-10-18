from types import SimpleNamespace
from typing import Any

import pytest
from agents.llm_client import LlmClient, LlmError, from_env
from openai import APITimeoutError


class FakeCompletions:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ready"))],
            usage=SimpleNamespace(prompt_tokens=5, completion_tokens=1),
        )


def make_client(messages: FakeCompletions) -> LlmClient:
    fake: Any = SimpleNamespace(chat=SimpleNamespace(completions=messages))
    return LlmClient(
        "https://example.services.ai.azure.com/anthropic", "dep", client=fake
    )


def test_complete_returns_text_and_deployment() -> None:
    messages = FakeCompletions()
    reply = make_client(messages).complete("hi")
    assert (reply.text, reply.model) == ("ready", "dep")
    assert messages.calls[0]["model"] == "dep"


def test_failure_becomes_llm_error_with_class_name() -> None:
    import httpx

    error = APITimeoutError(request=httpx.Request("POST", "https://example.invalid"))
    with pytest.raises(LlmError) as info:
        make_client(FakeCompletions(error)).complete("hi")
    assert info.value.cause_name == "APITimeoutError"


def test_from_env_requires_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MODEL_BASE_URL", raising=False)
    monkeypatch.delenv("MODEL_DEPLOYMENT_NAME", raising=False)
    with pytest.raises(LlmError):
        from_env()
