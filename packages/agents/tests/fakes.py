"""A fake chat client that replays scripted replies, and fact builders."""

import json
from typing import Any

from agents.llm_client import LlmError, LlmReply, ResponseFormat
from contracts.models import Fact


class FakeChat:
    def __init__(
        self, replies: list[str | dict[str, Any] | Exception], deployment: str = "fake"
    ) -> None:
        self.deployment = deployment
        self.response_format: ResponseFormat = "none"
        self.replies = list(replies)
        self.prompts: list[str] = []

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int = 256,
        system: str | None = None,
        json_schema: dict[str, Any] | None = None,
        timeout_s: float | None = None,
    ) -> LlmReply:
        self.prompts.append(prompt)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        text = reply if isinstance(reply, str) else json.dumps(reply)
        return LlmReply(text, self.deployment, 5, 10, 4)


def timeout() -> LlmError:
    return LlmError("APITimeoutError")


def fact(
    fact_id: str, *display: str, side: str | None = None, value: float = 1
) -> Fact:
    return Fact.model_validate(
        {
            "id": fact_id,
            "name": f"test({fact_id})",
            "value": value,
            "display": {"en": list(display)},
            "scope": {"side": side} if side else None,
            "source_ids": ["ev-000001"],
            "extractor": {"name": "test", "version": "1"},
        }
    )


def bundle_of(*facts: Fact) -> dict[str, Fact]:
    return {f.id.root: f for f in facts}


TEAMS = {"home": "Ashford", "away": "Rivermouth"}
