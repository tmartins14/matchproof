"""Corrections by consensus: when the auditor disagrees, the inline judge looks again.

The auditor (a second vendor) is log-only on its own. It can correct a claim already on air only if
the inline judge, asked again with the auditor's problem and reason in front of it, now agrees:

- the re-check agrees with the auditor: the Narrator rewrites the claim once, with both reasons. If
  the new wording passes the full check (reconcile, lint, judge) it replaces the old text with
  verdict `rephrased`; if it cannot be fixed the verdict becomes `blocked`;
- the re-check still disagrees with the auditor: nothing changes on screen and the disagreement is
  logged as unresolved.

A correction always carries the previous text, so the viewer sees what changed. Each claim is
reviewed at most once; the caller enforces that and the token cap.
"""

import asyncio
from dataclasses import dataclass
from typing import Any, Literal

from contracts.models import Audit, Claim, Fact
from opentelemetry import trace

from .checker import (
    JUDGE_MAX_TOKENS,
    JUDGE_TIMEOUT_S,
    Checker,
    JudgeAnswer,
    render_judge_prompt,
)
from .llm_client import ChatClient, LlmError
from .narrator import DraftClaim, Revision, narrate
from .pipeline import ToolServer, tool_result
from .structured import StructuredOutputError, complete_structured

MAX_REASON_CHARS = 400
MODEL_ERRORS = (LlmError, StructuredOutputError)
_tracer = trace.get_tracer(__name__)

Kind = Literal["corrected", "blocked", "unresolved"]


@dataclass(frozen=True)
class Outcome:
    kind: Kind
    note: str  # one plain line for the Producer log
    claim: Claim | None = None  # the replacement, for corrected and blocked
    recheck_reason: str = ""  # what the inline judge said when asked again


def recheck_prompt(base: str, audit: Audit) -> str:
    """The judge prompt with the second reviewer's finding added."""
    return (
        f"{base}\n\nA second reviewer raised this about the sentence"
        f" ({audit.problem or 'unsupported'}): {audit.reason or 'no reason given'}\n"
        "Decide if it is right. Answer supported = false if the reviewer is right and the sentence "
        "says more than the facts; answer supported = true if the sentence stays within the facts."
    )


class Consensus:
    def __init__(
        self,
        judge: ChatClient,
        narrator: ChatClient,
        server: ToolServer,
        *,
        timeout_s: float = JUDGE_TIMEOUT_S,
    ) -> None:
        self._judge = judge
        self._narrator = narrator
        self._server = server
        self._timeout_s = timeout_s

    async def review(
        self, match_id: str, claim: Claim, audit: Audit, at_t: float
    ) -> Outcome:
        """Decide what the auditor's disagreement with `claim` comes to. Never raises for a model
        error: a re-check that cannot be made leaves the claim as it is."""
        with _tracer.start_as_current_span(
            "consensus", attributes={"matchproof.claim_id": claim.id.root}
        ) as span:
            outcome = await self._review(match_id, claim, audit, at_t)
            span.set_attribute("matchproof.consensus.outcome", outcome.kind)
            return outcome

    async def _review(
        self, match_id: str, claim: Claim, audit: Audit, at_t: float
    ) -> Outcome:
        label = claim.id.root
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
            return Outcome(
                "unresolved",
                f"{label} could not be re-checked: its facts could not be read.",
            )
        teams = {"home": brief["home"]["name"], "away": brief["away"]["name"]}
        facts = {
            f["id"]: Fact.model_validate({k: v for k, v in f.items() if k != "label"})
            for f in bundle["facts"]
        }
        labels = {f["id"]: f["label"] for f in bundle["facts"]}
        names = {p["name"] for s in ("home", "away") for p in brief[s]["players"]}
        beat = bundle["beat"]
        cited = [facts[f.root] for f in claim.fact_ids if f.root in facts]

        prompt = recheck_prompt(
            render_judge_prompt(
                claim.text, cited, teams, beat["kind"], beat["label"], labels
            ),
            audit,
        )
        try:
            reply = await asyncio.to_thread(
                complete_structured,
                self._judge,
                JudgeAnswer,
                prompt,
                max_tokens=JUDGE_MAX_TOKENS,
                timeout_s=self._timeout_s,
            )
        except MODEL_ERRORS as exc:
            return Outcome(
                "unresolved",
                f"{label} could not be re-checked: {type(exc).__name__}.",
            )
        answer = reply.value
        if answer.supported:
            return Outcome(
                "unresolved",
                f"The second model disagrees on {label} ({audit.problem}) but the judge, asked again, "
                f"keeps it: {answer.reason}",
                recheck_reason=answer.reason,
            )

        # Both reviewers say the claim is wrong: one rewrite, checked in full.
        reasons = [
            f"Second reviewer ({audit.problem or 'unsupported'}): {audit.reason}",
            f"Judge, asked again ({answer.problem or 'unsupported'}): {answer.reason}",
        ]
        revision = Revision(
            draft=[
                DraftClaim.model_construct(
                    text=claim.text, fact_ids=[f.root for f in claim.fact_ids]
                )
            ],
            reasons=reasons,
            kept=[],
        )
        new: DraftClaim | None = None
        try:
            out = await asyncio.to_thread(
                narrate, self._narrator, bundle, "fan", teams=teams, revise=revision
            )
            new = out.value.claims[0]
        except MODEL_ERRORS:
            new = None
        correction = {
            "at_t": at_t,
            "previous_text": claim.text,
            "reason": (audit.reason or "")[:MAX_REASON_CHARS],
            "by": [audit.deployment, self._judge.deployment],
        }
        why = "; ".join(reasons)[:MAX_REASON_CHARS]
        if new is not None and new.text.strip().lower() != claim.text.strip().lower():
            checker = Checker(self._judge, timeout_s=self._timeout_s)
            check = await asyncio.to_thread(
                checker.check_one,
                new,
                facts,
                teams=teams,
                beat_kind=beat["kind"],
                beat_label=beat["label"],
                labels=labels,
                names=names,
            )
            if check.passed:
                fixed = self._rebuilt(
                    claim,
                    correction,
                    verdict="rephrased",
                    text=new.text,
                    fact_ids=check.fact_ids,
                    numbers=[
                        {"as_written": n.as_written, "fact_id": n.fact_id}
                        for n in check.numbers
                    ],
                    reason=why,
                    checker={"reconciled": check.reconciled, "judge_supported": True},
                )
                return Outcome(
                    "corrected",
                    f"{label} was corrected after the second model and the judge agreed ({audit.problem}).",
                    fixed,
                    answer.reason,
                )
        blocked = self._rebuilt(
            claim,
            correction,
            verdict="blocked",
            text=claim.text,
            fact_ids=[f.root for f in claim.fact_ids],
            numbers=None,
            reason=why,
            checker=None,
        )
        return Outcome(
            "blocked",
            f"{label} was blocked after the second model and the judge agreed ({audit.problem}); no honest rewording passed.",
            blocked,
            answer.reason,
        )

    @staticmethod
    def _rebuilt(
        claim: Claim,
        correction: dict[str, Any],
        *,
        verdict: str,
        text: str,
        fact_ids: list[str],
        numbers: list[dict[str, str]] | None,
        reason: str,
        checker: dict[str, Any] | None,
    ) -> Claim:
        data: dict[str, Any] = claim.model_dump(
            mode="json", by_alias=True, exclude_none=True
        )
        data.pop("audit", None)  # the audit was of the old text
        data.update(
            verdict=verdict,
            text=text,
            fact_ids=fact_ids,
            reason=reason,
            draft_text=claim.text,
            correction=correction,
        )
        if numbers is not None:
            data["numbers"] = numbers
        if checker is not None:
            data["checker"] = {**data.get("checker", {}), **checker}
        return Claim.model_validate(data)
