"""The single seam between agents and the model SDK.

Callers depend on `LlmClient.complete`; swapping the model or SDK only touches this module.
Auth is Microsoft Entra ID via `DefaultAzureCredential` (managed identity in Azure, `az login`
locally). No keys.
"""

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol
from urllib.parse import urlparse

import yaml
from azure.core.credentials import TokenCredential
from azure.core.exceptions import AzureError
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import OpenAI, OpenAIError
from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode

TOKEN_SCOPE = "https://ai.azure.com/.default"
DEFAULT_TIMEOUT_S = 15.0

MODELS_PATH = Path(__file__).resolve().parents[2] / "config" / "models.yaml"
JUDGE_DEPLOYMENT_ENV = "JUDGE_DEPLOYMENT"

Role = Literal["narrator", "judge", "producer", "auditor", "composer"]
# How a deployment returns JSON: a response_format JSON schema, JSON mode, or only by prompt.
ResponseFormat = Literal["json_schema", "json_object", "none"]

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
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class ModelSettings:
    """One deployment's call settings, from config/models.yaml."""

    deployment: str
    max_output_tokens: int = 512
    timeout_s: float = DEFAULT_TIMEOUT_S
    response_format: ResponseFormat = "none"
    temperature: float | None = None  # None where the deployment only takes its default
    reasoning_effort: str | None = None


class ChatClient(Protocol):
    """What the agents need from a client; tests pass a fake."""

    deployment: str
    response_format: ResponseFormat

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int = 256,
        system: str | None = None,
        json_schema: dict[str, Any] | None = None,
        timeout_s: float | None = None,
    ) -> LlmReply: ...


class LlmClient:
    def __init__(
        self,
        base_url: str,
        deployment: str,
        *,
        credential: TokenCredential | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        client: OpenAI | None = None,
        settings: ModelSettings | None = None,
    ) -> None:
        self.deployment = deployment
        self.settings = settings or ModelSettings(
            deployment, reasoning_effort="minimal"
        )
        self.response_format: ResponseFormat = self.settings.response_format
        self._server = urlparse(base_url).hostname or ""
        if client is None:
            provider = get_bearer_token_provider(
                credential or DefaultAzureCredential(), TOKEN_SCOPE
            )
            client = OpenAI(
                base_url=base_url,
                api_key=provider,
                timeout=timeout_s,
                max_retries=0,
            )
        self._client = client

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int = 256,
        system: str | None = None,
        json_schema: dict[str, Any] | None = None,
        timeout_s: float | None = None,
    ) -> LlmReply:
        """One chat completion. `json_schema` is used only where the deployment supports it."""
        started = time.perf_counter()
        extra: dict[str, Any] = {}
        if self.settings.reasoning_effort is not None:
            extra["reasoning_effort"] = self.settings.reasoning_effort
        if self.settings.temperature is not None:
            extra["temperature"] = self.settings.temperature
        if self.response_format == "json_schema" and json_schema is not None:
            extra["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "reply",
                    "strict": False,
                    "schema": json_schema,
                },
            }
        elif self.response_format == "json_object":
            extra["response_format"] = {"type": "json_object"}
        if timeout_s is not None:
            extra["timeout"] = timeout_s
        messages: list[dict[str, str]] = [{"role": "user", "content": prompt}]
        if system is not None:
            messages.insert(0, {"role": "system", "content": system})
        with _tracer.start_as_current_span(
            f"chat {self.deployment}",
            kind=SpanKind.CLIENT,
            attributes={
                "gen_ai.system": "az.ai.openai",
                "gen_ai.operation.name": "chat",
                "gen_ai.request.model": self.deployment,
                "server.address": self._server,
            },
        ) as span:
            try:
                completion = self._client.chat.completions.create(
                    model=self.deployment,
                    # Reasoning models spend part of this budget on hidden reasoning tokens.
                    max_completion_tokens=max_tokens,
                    messages=messages,  # type: ignore[arg-type]
                    **extra,
                )
            except (OpenAIError, AzureError) as exc:
                span.set_status(Status(StatusCode.ERROR, type(exc).__name__))
                span.set_attribute("error.type", type(exc).__name__)
                raise LlmError(type(exc).__name__) from exc
            if completion.usage:
                span.set_attribute(
                    "gen_ai.usage.input_tokens", completion.usage.prompt_tokens
                )
                span.set_attribute(
                    "gen_ai.usage.output_tokens", completion.usage.completion_tokens
                )
        text = (
            (completion.choices[0].message.content or "") if completion.choices else ""
        )
        return LlmReply(
            text=text,
            model=self.deployment,
            latency_ms=round((time.perf_counter() - started) * 1000),
            input_tokens=completion.usage.prompt_tokens if completion.usage else 0,
            output_tokens=completion.usage.completion_tokens if completion.usage else 0,
        )


def from_env() -> LlmClient:
    """Build a client from MODEL_BASE_URL and MODEL_DEPLOYMENT_NAME."""
    base_url = os.environ.get("MODEL_BASE_URL")
    deployment = os.environ.get("MODEL_DEPLOYMENT_NAME")
    if not base_url or not deployment:
        raise LlmError("MissingModelConfig")
    return LlmClient(base_url, deployment)


def load_models(path: Path | None = None) -> dict[str, Any]:
    raw: dict[str, Any] = yaml.safe_load((path or MODELS_PATH).read_text("utf-8"))
    return raw


def settings_for(entry: dict[str, Any]) -> ModelSettings:
    return ModelSettings(**entry)


def judge_settings(
    models: dict[str, Any], deployment: str | None = None
) -> ModelSettings:
    """The judge's settings: `deployment`, else JUDGE_DEPLOYMENT, else the active judge."""
    name = deployment or os.environ.get(JUDGE_DEPLOYMENT_ENV)
    if not name or name == models["judge"]["deployment"]:
        return settings_for(models["judge"])
    known = [*models["judge_candidates"], models["judge_fallback"]]
    entry = next((e for e in known if e["deployment"] == name), None)
    if entry is None:
        raise LlmError("UnknownJudgeDeployment")
    return settings_for(entry)


def client_for(role: Role, *, deployment: str | None = None) -> LlmClient:
    """A client for a role, configured from config/models.yaml. `deployment` picks another judge
    (the bake-off); otherwise the judge is JUDGE_DEPLOYMENT or the one set in the file."""
    base_url = os.environ.get("MODEL_BASE_URL")
    if not base_url:
        raise LlmError("MissingModelConfig")
    models = load_models()
    settings = (
        judge_settings(models, deployment)
        if role == "judge"
        else settings_for(models[role])
    )
    return LlmClient(
        base_url,
        settings.deployment,
        timeout_s=settings.timeout_s,
        settings=settings,
    )
