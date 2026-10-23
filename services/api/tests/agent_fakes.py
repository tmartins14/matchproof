"""Fake model clients that answer by what the prompt asks, so concurrent beats need no script."""

import json
import re
import threading
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from agents.llm_client import LlmError, LlmReply, ResponseFormat
from api.agents_runtime import AgentRuntime, SessionServer
from api.matchdata import get_internal_server
from mcp.shared.memory import create_connected_server_and_client_session
from mcp_match import InMemoryMatchStore

FACT_LINE = re.compile(r"^- (fx-\S+) \|", re.MULTILINE)


class FakeModel:
    """Answers the Producer, Narrator and judge prompts. Counts calls; can be slow or failing."""

    def __init__(
        self,
        deployment: str = "fake",
        *,
        narrate: bool = True,
        supported: bool = True,
        delay_s: float = 0.0,
        error: Exception | None = None,
        gate: threading.Event | None = None,
    ) -> None:
        self.deployment = deployment
        self.response_format: ResponseFormat = "none"
        self.narrate = narrate
        self.supported = supported
        self.delay_s = delay_s
        self.error = error
        self.gate = gate
        self.calls = 0
        self.started = 0
        self._lock = threading.Lock()

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int = 256,
        system: str | None = None,
        json_schema: dict[str, Any] | None = None,
        timeout_s: float | None = None,
    ) -> LlmReply:
        with self._lock:
            self.started += 1
        if self.gate is not None:
            self.gate.wait(30)
        if self.delay_s:
            time.sleep(self.delay_s)
        if self.error is not None:
            raise self.error
        with self._lock:
            self.calls += 1
        if "You are the producer" in prompt:
            body: dict[str, Any] = {
                "narrate": self.narrate,
                "priority": 3,
                "note": "Something new to show.",
            }
        elif "Sentence:" in prompt:
            body = {
                "supported": self.supported,
                "problem": None if self.supported else "overclaim",
                "reason": "Matches." if self.supported else "Says more than the facts.",
            }
        else:
            fact_id = FACT_LINE.search(prompt)
            assert fact_id is not None, prompt[:200]
            body = {
                "claims": [
                    {"text": "A moment worth a look.", "fact_ids": [fact_id.group(1)]}
                ]
            }
        return LlmReply(json.dumps(body), self.deployment, 5, 10, 4)


@asynccontextmanager
async def agent_runtime(
    *,
    narrator: FakeModel | None = None,
    judge: FakeModel | None = None,
    producer: FakeModel | None = None,
    auditor: FakeModel | None = None,
) -> AsyncIterator[tuple[AgentRuntime, InMemoryMatchStore]]:
    store = InMemoryMatchStore()
    internal = get_internal_server(store)
    async with create_connected_server_and_client_session(
        internal._mcp_server
    ) as session:
        yield (
            AgentRuntime(
                SessionServer(session),
                narrator=narrator or FakeModel("fake-narrator"),
                judge=judge or FakeModel("fake-judge"),
                producer=producer or FakeModel("fake-producer"),
                auditor=auditor,
            ),
            store,
        )


def rate_limited() -> LlmError:
    return LlmError("RateLimitError")


class ConsensusJudge(FakeModel):
    """The inline judge for the consensus tests: it passes every claim, except that asked again
    after a second reviewer's finding it agrees with the reviewer (or not), and it can refuse the
    rewrite."""

    def __init__(
        self,
        deployment: str = "fake-judge",
        *,
        agrees_on_recheck: bool = True,
        refuses_rewrite: bool = False,
    ) -> None:
        super().__init__(deployment)
        self.agrees_on_recheck = agrees_on_recheck
        self.refuses_rewrite = refuses_rewrite
        self.rechecks = 0

    def complete(self, prompt: str, **kwargs: Any) -> LlmReply:
        if "A second reviewer raised this" in prompt:
            with self._lock:
                self.rechecks += 1
            supported = not self.agrees_on_recheck
        else:
            supported = not (self.refuses_rewrite and REWRITE in prompt)
        body = {
            "supported": supported,
            "problem": None if supported else "overclaim",
            "reason": "Matches." if supported else "Says more than the facts.",
        }
        return LlmReply(json.dumps(body), self.deployment, 5, 10, 4)


REWRITE = "A shot is blocked."


class RewritingNarrator(FakeModel):
    """Drafts one claim; asked to revise a rejected one, it answers with a different claim."""

    def complete(self, prompt: str, **kwargs: Any) -> LlmReply:
        if "was rejected by the Checker" not in prompt:
            return super().complete(prompt, **kwargs)
        fact_id = FACT_LINE.search(prompt)
        assert fact_id is not None
        body = {"claims": [{"text": REWRITE, "fact_ids": [fact_id.group(1)]}]}
        return LlmReply(json.dumps(body), self.deployment, 5, 10, 4)
