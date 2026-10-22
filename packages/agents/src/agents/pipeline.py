"""One beat through Narrator and Checker, and the claims written back.

A plain async function so the live stream and the Agent Framework workflow can call it. The
agents reach the match only through the internal MCP server (ADR 0008): the bundle comes from
`get_beat_bundle` and the claims go back through `put_claims`.
"""

import asyncio
import json
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from contracts.models import Claim, Fact
from opentelemetry import trace
from opentelemetry.trace import Span

from .checker import CheckedClaim, Checker
from .llm_client import ChatClient
from .narrator import DraftClaim, Mode, NarratorOutput, Revision, narrate
from .structured import Structured

_tracer = trace.get_tracer(__name__)


class ToolServer(Protocol):
    """The internal MCP server (a FastMCP instance, or a fake in tests)."""

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any: ...


@dataclass
class Deps:
    server: ToolServer
    narrator: ChatClient
    judge: ChatClient


@dataclass
class BeatRun:
    claims: list[Claim]
    checked: list[CheckedClaim]
    latency_ms: int
    narrator_tokens: int = 0
    judge_tokens: int = 0
    narrator_calls: list[Structured[NarratorOutput]] = field(default_factory=list)


def tool_result(raw: Any) -> dict[str, Any]:
    """The structured result of an MCP tool call, however the server packaged it."""
    if isinstance(raw, tuple):  # (content, structured)
        raw = raw[1] if isinstance(raw[1], dict) else raw[0]
    if isinstance(raw, dict):
        return raw
    seq: Sequence[Any] = raw
    parsed: dict[str, Any] = json.loads(seq[0].text)
    return parsed


def _span_attrs(span: Span, **attrs: str | float) -> None:
    for key, value in attrs.items():
        span.set_attribute(key, value)


async def run_beat(match_id: str, beat_id: str, mode: Mode, *, deps: Deps) -> BeatRun:
    started = time.perf_counter()
    with _tracer.start_as_current_span(
        "invoke_agent narrate_and_check",
        attributes={
            "gen_ai.operation.name": "invoke_agent",
            "gen_ai.agent.name": "narrate_and_check",
            "matchproof.match_id": match_id,
            "matchproof.beat_id": beat_id,
            "matchproof.mode": mode,
        },
    ) as root:
        with _tracer.start_as_current_span("fetch_bundle"):
            bundle = tool_result(
                await deps.server.call_tool(
                    "get_beat_bundle", {"match_id": match_id, "beat_id": beat_id}
                )
            )
            brief = tool_result(
                await deps.server.call_tool("get_brief", {"match_id": match_id})
            )
        teams = {"home": brief["home"]["name"], "away": brief["away"]["name"]}
        labels = {f["id"]: f["label"] for f in bundle["facts"]}
        facts = {
            f["id"]: Fact.model_validate({k: v for k, v in f.items() if k != "label"})
            for f in bundle["facts"]
        }
        beat = bundle["beat"]
        calls: list[Structured[NarratorOutput]] = []

        def draft(revision: Revision | None) -> list[DraftClaim]:
            with _tracer.start_as_current_span(
                "narrate",
                attributes={
                    "gen_ai.operation.name": "chat",
                    "gen_ai.request.model": deps.narrator.deployment,
                    "matchproof.retry": revision is not None,
                },
            ) as span:
                out = narrate(deps.narrator, bundle, mode, teams=teams, revise=revision)
                _span_attrs(
                    span,
                    **{
                        "gen_ai.usage.input_tokens": out.input_tokens,
                        "gen_ai.usage.output_tokens": out.output_tokens,
                    },
                )
            calls.append(out)
            return out.value.claims

        drafts = await asyncio.to_thread(draft, None)
        checker = Checker(deps.judge)

        def check() -> list[CheckedClaim]:
            with _tracer.start_as_current_span(
                "check",
                attributes={"gen_ai.request.model": deps.judge.deployment},
            ) as span:
                result = checker.check_beat(
                    drafts,
                    facts,
                    beat_id=beat_id,
                    lang="en",
                    teams=teams,
                    beat_kind=beat["kind"],
                    beat_label=beat["label"],
                    labels=labels,
                    renarrate=lambda rev: draft(rev),
                )
                _span_attrs(
                    span,
                    **{
                        "matchproof.verdicts": ",".join(
                            c.claim.verdict.value for c in result
                        )
                    },
                )
            return result

        checked = await asyncio.to_thread(check)
        claims = [c.claim for c in checked]
        with _tracer.start_as_current_span("put_claims"):
            written = tool_result(
                await deps.server.call_tool(
                    "put_claims",
                    {
                        "match_id": match_id,
                        "beat_id": beat_id,
                        "claims": [
                            c.model_dump(mode="json", by_alias=True, exclude_none=True)
                            for c in claims
                        ],
                    },
                )
            )
        rejected = [r for r in written["results"] if not r["accepted"]]
        if rejected:
            raise ValueError(f"put_claims rejected claims: {rejected}")
        latency_ms = round((time.perf_counter() - started) * 1000)
        _span_attrs(root, **{"matchproof.beat.latency_ms": latency_ms})
    return BeatRun(
        claims=claims,
        checked=checked,
        latency_ms=latency_ms,
        narrator_tokens=sum(c.input_tokens + c.output_tokens for c in calls),
        judge_tokens=sum(
            c.final.input_tokens
            + c.first.input_tokens
            + c.final.output_tokens
            + c.first.output_tokens
            for c in checked
        ),
        narrator_calls=calls,
    )


async def narrate_and_check(
    match_id: str, beat_id: str, mode: Mode, *, deps: Deps
) -> list[Claim]:
    """Fetch the beat's bundle, narrate, check and write. Returns the claims as stored."""
    return (await run_beat(match_id, beat_id, mode, deps=deps)).claims
