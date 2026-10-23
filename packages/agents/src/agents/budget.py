"""A process-wide daily token counter. When it trips, narration pauses; auditing stops first.

The cap comes from DAILY_TOKEN_CAP (default 2_000_000). The count resets at the first use on a new
UTC day. Every model call made through `MeteredClient` is counted, whichever agent made it.
"""

import os
import threading
from collections import OrderedDict
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from .llm_client import ChatClient, LlmError, LlmReply
from .prices import cost_of

DAILY_TOKEN_CAP = 2_000_000
CAP_ENV = "DAILY_TOKEN_CAP"
AUDIT_STOP_FRACTION = (
    0.9  # auditing stops at this share of the cap, so narration outlives it
)


# The match whose work a model call belongs to. MatchRun sets it around the tasks it starts; the
# tasks and the threads they use inherit it, so usage can be told per match.
current_match: ContextVar[str | None] = ContextVar("current_match", default=None)
MAX_TRACKED_MATCHES = 50


class TokenBudget:
    def __init__(self, cap: int | None = None) -> None:
        self._cap = cap
        self._lock = threading.Lock()
        self._day = self._today()
        self._used: dict[str, int] = {}
        self._split: dict[str, dict[str, Any]] = {}  # role: {deployment, input, output}
        self._by_match: OrderedDict[str, dict[str, dict[str, Any]]] = OrderedDict()

    @staticmethod
    def _today() -> str:
        return datetime.now(UTC).date().isoformat()

    @property
    def cap(self) -> int:
        if self._cap is not None:
            return self._cap
        return int(os.environ.get(CAP_ENV, DAILY_TOKEN_CAP))

    def _roll(self) -> None:
        today = self._today()
        if today != self._day:
            self._day, self._used, self._split = today, {}, {}

    def add(
        self,
        role: str,
        tokens: int,
        *,
        deployment: str | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        """Count tokens for a role. With the deployment and the input/output split, cost can follow."""
        with self._lock:
            self._roll()
            self._used[role] = self._used.get(role, 0) + tokens
            if deployment is not None:
                u = self._split.setdefault(
                    role, {"deployment": deployment, "input": 0, "output": 0}
                )
                u["input"] += input_tokens
                u["output"] += output_tokens
                match_id = current_match.get()
                if match_id is not None:
                    per = self._by_match.setdefault(match_id, {})
                    self._by_match.move_to_end(match_id)
                    m = per.setdefault(
                        role, {"deployment": deployment, "input": 0, "output": 0}
                    )
                    m["input"] += input_tokens
                    m["output"] += output_tokens
                    while len(self._by_match) > MAX_TRACKED_MATCHES:
                        self._by_match.popitem(last=False)

    def match_usage(self, match_id: str) -> dict[str, Any]:
        """Tokens and cost for one match: {usage: {role: {deployment, input, output}}, cost}."""
        with self._lock:
            usage = {r: dict(u) for r, u in self._by_match.get(match_id, {}).items()}
        return {"match_id": match_id, "usage": usage, "cost": cost_of(usage)}

    @property
    def used(self) -> int:
        with self._lock:
            self._roll()
            return sum(self._used.values())

    @property
    def narration_paused(self) -> bool:
        return self.used >= self.cap

    @property
    def auditing_stopped(self) -> bool:
        return self.used >= self.cap * AUDIT_STOP_FRACTION

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            self._roll()
            used = sum(self._used.values())
            return {
                "day": self._day,
                "cap": self.cap,
                "used": used,
                "by_role": dict(self._used),
                "usage": {r: dict(u) for r, u in self._split.items()},
                "cost": cost_of(self._split),
                "narration_paused": used >= self.cap,
                "auditing_stopped": used >= self.cap * AUDIT_STOP_FRACTION,
            }


budget = TokenBudget()


class MeteredClient:
    """A ChatClient that counts tokens against the daily budget and refuses calls once it is spent.

    Auditor calls refuse at `AUDIT_STOP_FRACTION` of the cap; every other role at the cap.
    """

    def __init__(
        self, inner: ChatClient, role: str, *, counter: TokenBudget | None = None
    ):
        self._inner = inner
        self._role = role
        self._budget = counter or budget
        self.deployment = inner.deployment
        self.response_format = inner.response_format

    def complete(self, prompt: str, **kwargs: Any) -> LlmReply:
        stopped = (
            self._budget.auditing_stopped
            if self._role == "auditor"
            else self._budget.narration_paused
        )
        if stopped:
            raise LlmError("DailyTokenCap")
        reply = self._inner.complete(prompt, **kwargs)
        self._budget.add(
            self._role,
            reply.input_tokens + reply.output_tokens,
            deployment=self.deployment,
            input_tokens=reply.input_tokens,
            output_tokens=reply.output_tokens,
        )
        return reply
