"""A process-wide daily token counter. When it trips, narration pauses; auditing stops first.

The cap comes from DAILY_TOKEN_CAP (default 2_000_000). The count resets at the first use on a new
UTC day. Every model call made through `MeteredClient` is counted, whichever agent made it.
"""

import os
import threading
from datetime import UTC, datetime
from typing import Any

from .llm_client import ChatClient, LlmError, LlmReply
from .prices import cost_of

DAILY_TOKEN_CAP = 2_000_000
CAP_ENV = "DAILY_TOKEN_CAP"
AUDIT_STOP_FRACTION = (
    0.9  # auditing stops at this share of the cap, so narration outlives it
)


class TokenBudget:
    def __init__(self, cap: int | None = None) -> None:
        self._cap = cap
        self._lock = threading.Lock()
        self._day = self._today()
        self._used: dict[str, int] = {}
        self._split: dict[str, dict[str, Any]] = {}  # role: {deployment, input, output}

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
