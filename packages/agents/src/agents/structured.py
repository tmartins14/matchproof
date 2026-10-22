"""Ask a model for JSON that matches a Pydantic model, and validate it.

Uses a response_format JSON schema where the deployment supports it and JSON mode otherwise; for a
deployment with neither, the schema goes in the prompt. Invalid output gets one retry with the
validation error appended, then raises.
"""

import json
import re
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError

from .llm_client import ChatClient, LlmReply

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


class StructuredOutputError(Exception):
    """The model's reply was not valid for the requested model, even after one retry."""


@dataclass(frozen=True)
class Structured[T: BaseModel]:
    value: T
    model: str
    latency_ms: int  # all attempts
    input_tokens: int
    output_tokens: int
    attempts: int


def parse(model_cls: type[BaseModel], text: str) -> BaseModel:
    """Validate a reply as `model_cls`; tolerates a code fence around the JSON."""
    body = _FENCE_RE.sub("", text.strip())
    try:
        return model_cls.model_validate_json(body)
    except ValidationError:
        # Some models wrap the object in prose; take the outermost braces.
        start, end = body.find("{"), body.rfind("}")
        if start == -1 or end <= start:
            raise
        return model_cls.model_validate(json.loads(body[start : end + 1]))


def complete_structured[T: BaseModel](
    client: ChatClient,
    model_cls: type[T],
    prompt: str,
    *,
    system: str | None = None,
    max_tokens: int = 512,
    timeout_s: float | None = None,
) -> Structured[T]:
    schema = model_cls.model_json_schema()
    if client.response_format != "json_schema":
        prompt += (
            "\n\nReply with one JSON object only, no prose and no code fence, matching this "
            f"JSON Schema:\n{json.dumps(schema)}"
        )
    latency = tokens_in = tokens_out = 0
    attempt_prompt = prompt
    last_error = ""
    for attempt in (1, 2):
        reply: LlmReply = client.complete(
            attempt_prompt,
            max_tokens=max_tokens,
            system=system,
            json_schema=schema,
            timeout_s=timeout_s,
        )
        latency += reply.latency_ms
        tokens_in += reply.input_tokens
        tokens_out += reply.output_tokens
        try:
            value = parse(model_cls, reply.text)
        except (ValidationError, json.JSONDecodeError) as exc:
            last_error = str(exc)
            attempt_prompt = (
                f"{prompt}\n\nYour previous reply was invalid:\n{reply.text}\n\n"
                f"Validation error:\n{last_error}\n\nReply again with valid JSON only."
            )
            continue
        assert isinstance(value, model_cls)
        return Structured(value, reply.model, latency, tokens_in, tokens_out, attempt)
    raise StructuredOutputError(last_error)
