"""One beat through the workflow, and the claims written back.

`run_beat` and `narrate_and_check` are thin wrappers over the Agent Framework workflow in
`workflow.py` (Producer, Narrator, Checker), with a Producer that narrates every beat, so the evals
and scripts keep their one-call interface. The agents reach the match only through the internal MCP
server (ADR 0008): the bundle comes from `get_beat_bundle` and the claims go back through `put_claims`.
"""

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from contracts.models import Claim, Fact

from .checker import CheckedClaim
from .llm_client import ChatClient
from .narrator import Mode, NarratorOutput
from .producer import Decision, Producer
from .structured import Structured


class ToolServer(Protocol):
    """The internal MCP server (a FastMCP instance, or a fake in tests)."""

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any: ...


class Observer(Protocol):
    """Told how a beat is getting on, so the live stream can show claims as `checking` and then
    their verdicts. Called on the event loop."""

    def decided(self, beat_id: str, decision: Decision) -> None: ...

    def drafted(self, beat_id: str, previews: list[Claim]) -> None: ...

    def settled(self, beat_id: str, run: "BeatRun") -> None: ...


@dataclass
class Deps:
    server: ToolServer
    narrator: ChatClient
    judge: ChatClient
    producer: Producer | None = None  # None: every beat is narrated
    observer: Observer | None = None
    paused: Callable[[], bool] = lambda: (
        False
    )  # true when the daily token cap has tripped


@dataclass
class BeatRun:
    claims: list[Claim]
    checked: list[CheckedClaim]
    latency_ms: int
    narrator_tokens: int = 0
    judge_tokens: int = 0
    narrator_calls: list[Structured[NarratorOutput]] = field(default_factory=list)
    decision: Decision | None = None
    error: str | None = None  # why a narrated beat has no claims
    trace_id: str | None = None
    span_id: str | None = None


def tool_result(raw: Any) -> dict[str, Any]:
    """The structured result of an MCP tool call, however the server packaged it."""
    if isinstance(raw, tuple):  # (content, structured)
        raw = raw[1] if isinstance(raw[1], dict) else raw[0]
    if isinstance(raw, dict):
        return raw
    seq: Sequence[Any] = raw
    parsed: dict[str, Any] = json.loads(seq[0].text)
    return parsed


async def run_beat(match_id: str, beat_id: str, mode: Mode, *, deps: Deps) -> BeatRun:
    """Narrate and check one beat through the workflow, with every beat narrated."""
    from .workflow import run_beat_workflow  # the workflow imports this module's types

    return await run_beat_workflow(match_id, beat_id, mode, deps=deps)


async def narrate_and_check(
    match_id: str, beat_id: str, mode: Mode, *, deps: Deps
) -> list[Claim]:
    """Fetch the beat's bundle, narrate, check and write. Returns the claims as stored."""
    return (await run_beat(match_id, beat_id, mode, deps=deps)).claims
