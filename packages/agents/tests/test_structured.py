import pytest
from agents.structured import StructuredOutputError, complete_structured
from fakes import FakeChat
from pydantic import BaseModel


class Answer(BaseModel):
    ok: bool


def test_valid_reply_is_parsed_once() -> None:
    chat = FakeChat(['```json\n{"ok": true}\n```'])
    out = complete_structured(chat, Answer, "q")
    assert out.value.ok and out.attempts == 1 and len(chat.prompts) == 1


def test_invalid_reply_is_retried_once_with_the_error_then_succeeds() -> None:
    chat = FakeChat(["not json", {"ok": False}])
    out = complete_structured(chat, Answer, "q")
    assert out.attempts == 2 and not out.value.ok
    assert "not json" in chat.prompts[1] and "Validation error" in chat.prompts[1]


def test_two_invalid_replies_raise() -> None:
    chat = FakeChat(["nope", {"wrong": 1}])
    with pytest.raises(StructuredOutputError):
        complete_structured(chat, Answer, "q")
    assert len(chat.prompts) == 2
