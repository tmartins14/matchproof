"""The single seam between agents and the model SDK.

Callers depend on `LlmClient.complete`; swapping the model or SDK only touches this module.
Auth is Microsoft Entra ID via `DefaultAzureCredential` (managed identity in Azure, `az login`
locally). No keys.
"""

import os
import time
from dataclasses import dataclass
from urllib.parse import urlparse

from anthropic import AnthropicError, AnthropicFoundry
from azure.core.credentials import TokenCredential
from azure.core.exceptions import AzureError
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode

TOKEN_SCOPE = "https://ai.azure.com/.default"
DEFAULT_TIMEOUT_S = 15.0

_tracer = trace.get_tracer(__name__)


class LlmError(Exception):
    """A model call failed. `cause_name` is the class name of the underlying error."""

    def __init__(self, cause_name: str) -> None:
        super().__init__(cause_name)
        self.cause_name = cause_name


@dataclass(frozen=True)
class LlmReply:
    text: str
    model: str
    latency_ms: int


class LlmClient:
    def __init__(
        self,
        base_url: str,
        deployment: str,
        *,
        credential: TokenCredential | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        client: AnthropicFoundry | None = None,
    ) -> None:
        self.deployment = deployment
        self._server = urlparse(base_url).hostname or ""
        if client is None:
            provider = get_bearer_token_provider(
                credential or DefaultAzureCredential(), TOKEN_SCOPE
            )
            client = AnthropicFoundry(
                base_url=base_url,
                azure_ad_token_provider=provider,
                timeout=timeout_s,
                max_retries=0,
            )
        self._client = client

    def complete(self, prompt: str, *, max_tokens: int = 64) -> LlmReply:
        started = time.perf_counter()
        with _tracer.start_as_current_span(
            f"chat {self.deployment}",
            kind=SpanKind.CLIENT,
            attributes={
                "gen_ai.system": "anthropic",
                "gen_ai.operation.name": "chat",
                "gen_ai.request.model": self.deployment,
                "server.address": self._server,
            },
        ) as span:
            try:
                message = self._client.messages.create(
                    model=self.deployment,
                    max_tokens=max_tokens,
                    messages=[{"role": "user", "content": prompt}],
                )
            except (AnthropicError, AzureError) as exc:
                span.set_status(Status(StatusCode.ERROR, type(exc).__name__))
                span.set_attribute("error.type", type(exc).__name__)
                raise LlmError(type(exc).__name__) from exc
            span.set_attribute("gen_ai.usage.input_tokens", message.usage.input_tokens)
            span.set_attribute(
                "gen_ai.usage.output_tokens", message.usage.output_tokens
            )
        text = "".join(block.text for block in message.content if block.type == "text")
        return LlmReply(
            text=text,
            model=self.deployment,
            latency_ms=round((time.perf_counter() - started) * 1000),
        )


def from_env() -> LlmClient:
    """Build a client from MODEL_BASE_URL and MODEL_DEPLOYMENT_NAME."""
    base_url = os.environ.get("MODEL_BASE_URL")
    deployment = os.environ.get("MODEL_DEPLOYMENT_NAME")
    if not base_url or not deployment:
        raise LlmError("MissingModelConfig")
    return LlmClient(base_url, deployment)
