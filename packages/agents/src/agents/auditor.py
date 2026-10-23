"""The independent auditor: a second vendor runs the judge rubric on a claim the Checker settled.

Log-only. It never changes a published verdict and never delays the screen. The result is stored with
the claim through the internal MCP server (`put_audit`), and a disagreement goes to the Producer log,
the trace and the per-match audit summary.
"""

import asyncio
import time
from collections.abc import Sequence
from typing import Any

from contracts.models import Audit, Claim, Fact
from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.trace import Link, SpanContext

from .checker import JUDGE_MAX_TOKENS, JudgeAnswer, render_judge_prompt
from .llm_client import ChatClient, LlmError
from .pipeline import ToolServer, tool_result
from .structured import StructuredOutputError, complete_structured

AUDIT_TIMEOUT_S = 45.0
MAX_CONCURRENT_AUDITS = 2
RETRY_PAUSE_S = 2.0  # before the one retry after a 429 or a timeout
REASON_CHARS = 400
JUDGE_PROMPT = "judge.v2.md"  # the rubric the inline judge uses

_tracer = trace.get_tracer(__name__)


class Auditor:
    def __init__(
        self,
        client: ChatClient,
        server: ToolServer,
        *,
        timeout_s: float = AUDIT_TIMEOUT_S,
        retry_pause_s: float = RETRY_PAUSE_S,
    ) -> None:
        self._client = client
        self._server = server
        self._timeout_s = timeout_s
        self._retry_pause_s = retry_pause_s

    async def audit(
        self,
        match_id: str,
        claim: Claim,
        *,
        parent: Context | None = None,
        link: SpanContext | None = None,
    ) -> Audit:
        """Audit one settled claim and store the result. Never raises for a model error."""
        started = time.perf_counter()
        with _tracer.start_as_current_span(
            "audit",
            context=parent,
            links=[Link(link)] if link is not None else None,
            attributes={
                "matchproof.claim_id": claim.id.root,
                "gen_ai.request.model": self._client.deployment,
            },
        ) as span:
            result = await self._run(match_id, claim, started)
            span.set_attribute("matchproof.audit.outcome", result.outcome.value)
            if result.problem:
                span.set_attribute("matchproof.audit.problem", result.problem)
        await self._server.call_tool(
            "put_audit",
            {
                "match_id": match_id,
                "claim_id": claim.id.root,
                "audit": result.model_dump(mode="json", exclude_none=True),
            },
        )
        return result

    async def _run(self, match_id: str, claim: Claim, started: float) -> Audit:
        def done(outcome: str, **extra: Any) -> Audit:
            return Audit.model_validate(
                {
                    "deployment": self._client.deployment,
                    "outcome": outcome,
                    "latency_ms": round((time.perf_counter() - started) * 1000),
                    **extra,
                }
            )

        try:
            bundle = tool_result(
                await self._server.call_tool(
                    "get_beat_bundle",
                    {"match_id": match_id, "beat_id": claim.beat_id.root},
                )
            )
            brief = tool_result(
                await self._server.call_tool("get_brief", {"match_id": match_id})
            )
        except (OSError, ValueError, KeyError):
            return done("unavailable", reason="The facts could not be read.")
        teams = {"home": brief["home"]["name"], "away": brief["away"]["name"]}
        facts = {
            f["id"]: Fact.model_validate({k: v for k, v in f.items() if k != "label"})
            for f in bundle["facts"]
        }
        cited = [facts[f.root] for f in claim.fact_ids if f.root in facts]
        prompt = render_judge_prompt(
            claim.text,
            cited,
            teams,
            bundle["beat"]["kind"],
            bundle["beat"]["label"],
            {f["id"]: f["label"] for f in bundle["facts"]},
            JUDGE_PROMPT,
        )
        for attempt in (1, 2):
            try:
                reply = await asyncio.to_thread(
                    complete_structured,
                    self._client,
                    JudgeAnswer,
                    prompt,
                    max_tokens=JUDGE_MAX_TOKENS,
                    timeout_s=self._timeout_s,
                )
            except LlmError as exc:
                if exc.cause_name == "DailyTokenCap" or attempt == 2:
                    return done("unavailable", reason=exc.cause_name)
                await asyncio.sleep(self._retry_pause_s)
                continue
            except StructuredOutputError:
                return done("unavailable", reason="StructuredOutputError")
            answer = reply.value
            if answer.supported:
                return done("agree")
            return done(
                "disagree",
                problem=answer.problem or "unsupported",
                reason=answer.reason[:REASON_CHARS],
            )
        return done("unavailable")  # unreachable: the second attempt always returns


def summarize_audits(
    match_id: str,
    rows: Sequence[tuple[Claim, Audit, str]],
    corrections: Sequence[Claim] = (),
    unresolved: Sequence[tuple[Claim, str]] = (),
) -> dict[str, Any]:
    """How the auditor did on a match: claims audited, agreement rate, each disagreement with both
    judges' reasons (`rows` are the claim, its audit and what the inline judge said), and how many
    audits had no answer. `corrections` are the claims changed or blocked after a consensus
    re-check and `unresolved` the disagreements the re-check did not support (claim, what the judge
    said); the agreement rate after corrections counts a corrected disagreement as settled."""
    agreed = sum(1 for _, a, _ in rows if a.outcome.value == "agree")
    disagreed = [(c, a, r) for c, a, r in rows if a.outcome.value == "disagree"]
    audited = agreed + len(disagreed)
    return {
        "match_id": match_id,
        "claims_audited": audited,
        "agreement_rate": round(agreed / audited, 3) if audited else None,
        "agreement_rate_after_corrections": (
            round((agreed + len(corrections)) / audited, 3) if audited else None
        ),
        "corrections": [
            {
                "claim_id": c.id.root,
                "verdict": c.verdict.value,
                "previous_text": c.correction.previous_text if c.correction else None,
                "text": c.text,
                "reason": c.correction.reason if c.correction else None,
                "by": c.correction.by if c.correction else None,
                "at_t": c.correction.at_t if c.correction else None,
            }
            for c in corrections
        ],
        "unresolved": [
            {
                "claim_id": c.id.root,
                "text": c.text,
                "judge_on_recheck": judge_said,
            }
            for c, judge_said in unresolved
        ],
        "disagreements": [
            {
                "claim_id": c.id.root,
                "beat_id": c.beat_id.root,
                "fact_ids": [f.root for f in c.fact_ids],
                "text": c.text,
                "verdict": c.verdict.value,
                "checker": {
                    "deployment": c.checker.model if c.checker else None,
                    "reason": r,
                },
                "auditor": {
                    "deployment": a.deployment,
                    "problem": a.problem,
                    "reason": a.reason,
                },
            }
            for c, a, r in disagreed
        ],
        "unavailable": sum(1 for _, a, _ in rows if a.outcome.value == "unavailable"),
    }
