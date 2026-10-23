"""The agent workflow, built with the Microsoft Agent Framework: Producer, Narrator, Checker.

    Producer ──(narrate)──> Narrator ──> Checker ──> output
                               ^            │
                               └──(retry)───┘   taken at most once per claim

The Producer decides whether the beat is narrated (hard rules in `producer.py`); a skipped beat ends
there. The Narrator drafts claims from the beat's fact bundle. The Checker reconciles, lints and
judges them; the claims that fail go back to the Narrator once, with the reasons, and are checked
again. The steps are the Checker's own (`check_all`, `plan_retry`, `accept_revisions`, `settle`), so
the verdicts equal those of `Checker.check_beat`.

All match data comes through the internal MCP server (`get_beat_bundle`, `get_brief`, `put_claims`).
No agent imports the store or the fact registry.
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Never

from agent_framework import (
    Executor,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
    handler,
)
from contracts.models import Claim, Fact
from opentelemetry import trace
from opentelemetry.context import Context
from pydantic import ValidationError

from .checker import CheckedClaim, Checker, ClaimCheck
from .llm_client import LlmError
from .narrator import DraftClaim, Mode, Revision, narrate
from .pipeline import BeatRun, Deps, tool_result
from .producer import Decision
from .structured import Structured, StructuredOutputError

_tracer = trace.get_tracer(__name__)

MODEL_ERRORS = (LlmError, StructuredOutputError)


class TurnGate:
    """Lets the Producer decide beats one at a time, in the order they were found."""

    def __init__(self) -> None:
        self._next = 0
        self._released: set[int] = set()
        self._cond = asyncio.Condition()

    async def wait(self, ticket: int) -> None:
        async with self._cond:
            await self._cond.wait_for(lambda: self._next >= ticket)

    async def release(self, ticket: int) -> None:
        """Done with a turn, or giving it up. Safe to call twice and out of order."""
        async with self._cond:
            self._released.add(ticket)
            while self._next in self._released:
                self._released.discard(self._next)
                self._next += 1
            self._cond.notify_all()


@dataclass
class BeatJob:
    """What starts the workflow. The framework copies messages between executors, so they carry
    plain data only; the beat's span context and turn gate are looked up by `key`."""

    match_id: str
    beat_id: str
    mode: Mode
    ticket: int | None = None

    @property
    def key(self) -> str:
        return f"{self.match_id}/{self.beat_id}"

    @property
    def ctx(self) -> Context | None:
        """The beat's span context, so executors nest under it."""
        held = _running.get(self.key)
        return held[0] if held else None

    @property
    def gate(self) -> TurnGate | None:
        held = _running.get(self.key)
        return held[1] if held else None


_running: dict[str, tuple[Context, TurnGate | None]] = {}


@dataclass
class Briefed:
    """Producer to Narrator: the beat is on, with its bundle."""

    job: BeatJob
    bundle: dict[str, Any]
    teams: dict[str, str]
    names: set[str]
    labels: dict[str, str]
    facts: dict[str, Fact]
    decision: Decision
    started: float


@dataclass
class Drafted:
    """Narrator to Checker: the first drafts."""

    state: Briefed
    drafts: list[DraftClaim]
    calls: list[Structured[Any]] = field(default_factory=list)


@dataclass
class Revise:
    """Checker to Narrator: the failures and why. Taken at most once."""

    drafted: Drafted
    first: list[ClaimCheck]
    failed: list[int]
    revision: Revision


@dataclass
class Redrafted:
    """Narrator to Checker: the drafts that replace the failures."""

    revise: Revise
    new: list[DraftClaim]
    calls: list[Structured[Any]]


def _empty(state: Briefed, error: str | None = None) -> BeatRun:
    return BeatRun(
        [],
        [],
        round((time.perf_counter() - state.started) * 1000),
        decision=state.decision,
        error=error,
    )


class ProducerExecutor(Executor):
    def __init__(self, deps: Deps) -> None:
        super().__init__(id="producer")
        self._deps = deps

    @handler
    async def decide(
        self, job: BeatJob, ctx: WorkflowContext[Briefed, BeatRun]
    ) -> None:
        deps = self._deps
        started = time.perf_counter()
        with _tracer.start_as_current_span(
            "producer",
            context=job.ctx,
            attributes={
                "gen_ai.operation.name": "invoke_agent",
                "gen_ai.agent.name": "producer",
                "matchproof.beat_id": job.beat_id,
            },
        ) as span:
            if job.gate is not None and job.ticket is not None:
                await job.gate.wait(job.ticket)
            try:
                with _tracer.start_as_current_span("fetch_bundle"):
                    bundle = tool_result(
                        await deps.server.call_tool(
                            "get_beat_bundle",
                            {"match_id": job.match_id, "beat_id": job.beat_id},
                        )
                    )
                    brief = tool_result(
                        await deps.server.call_tool(
                            "get_brief", {"match_id": job.match_id}
                        )
                    )
                teams = {"home": brief["home"]["name"], "away": brief["away"]["name"]}
                beat = bundle["beat"]
                if deps.paused():
                    decision = Decision(
                        job.beat_id,
                        beat["kind"],
                        False,
                        1,
                        "Narration is paused for the day.",
                        reason="token_cap",
                    )
                elif deps.producer is not None:
                    decision = await asyncio.to_thread(
                        deps.producer.decide, beat, teams
                    )
                else:
                    decision = Decision(
                        job.beat_id, beat["kind"], True, 3, "Narrated.", reason="forced"
                    )
            finally:
                if job.gate is not None and job.ticket is not None:
                    await job.gate.release(job.ticket)
            span.set_attribute("matchproof.narrate", decision.narrate)
            span.set_attribute("matchproof.decided_by", decision.reason)
        if deps.observer is not None:
            deps.observer.decided(job.beat_id, decision)
        state = Briefed(
            job=job,
            bundle=bundle,
            teams=teams,
            names={
                p["name"] for side in ("home", "away") for p in brief[side]["players"]
            },
            labels={f["id"]: f["label"] for f in bundle["facts"]},
            facts={
                f["id"]: Fact.model_validate(
                    {k: v for k, v in f.items() if k != "label"}
                )
                for f in bundle["facts"]
            },
            decision=decision,
            started=started,
        )
        if decision.narrate:
            await ctx.send_message(state)
        else:
            await ctx.yield_output(_empty(state))


class NarratorExecutor(Executor):
    def __init__(self, deps: Deps) -> None:
        super().__init__(id="narrator")
        self._deps = deps

    async def _draft(
        self, state: Briefed, revision: Revision | None
    ) -> Structured[Any]:
        deps = self._deps
        with _tracer.start_as_current_span(
            "narrate",
            context=state.job.ctx,
            attributes={
                "gen_ai.operation.name": "chat",
                "gen_ai.request.model": deps.narrator.deployment,
                "matchproof.retry": revision is not None,
            },
        ) as span:
            out = await asyncio.to_thread(
                narrate,
                deps.narrator,
                state.bundle,
                state.job.mode,
                teams=state.teams,
                revise=revision,
            )
            span.set_attribute("gen_ai.usage.input_tokens", out.input_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", out.output_tokens)
        return out

    @handler
    async def write(
        self, state: Briefed, ctx: WorkflowContext[Drafted, BeatRun]
    ) -> None:
        try:
            out = await self._draft(state, None)
        except MODEL_ERRORS as exc:
            await ctx.yield_output(_empty(state, f"Narrator: {type(exc).__name__}"))
            return
        drafts = out.value.claims
        if self._deps.observer is not None:
            self._deps.observer.drafted(
                state.job.beat_id, previews(state.job.beat_id, drafts)
            )
        await ctx.send_message(Drafted(state, drafts, [out]))

    @handler
    async def rewrite(self, revise: Revise, ctx: WorkflowContext[Redrafted]) -> None:
        state = revise.drafted.state
        with _tracer.start_as_current_span("retry", context=state.job.ctx):
            try:
                out = await self._draft(state, revise.revision)
                new, calls = out.value.claims, [out]
            except MODEL_ERRORS:  # no fix arrives: the failed claims stay failed
                new, calls = [], []
        await ctx.send_message(Redrafted(revise, new, calls))


class CheckerExecutor(Executor):
    def __init__(self, deps: Deps) -> None:
        super().__init__(id="checker")
        self._deps = deps
        self._checker = Checker(deps.judge)

    def _check(self, state: Briefed, drafts: list[DraftClaim]) -> list[ClaimCheck]:
        with _tracer.start_as_current_span(
            "check",
            context=state.job.ctx,
            attributes={"gen_ai.request.model": self._deps.judge.deployment},
        ):
            return self._checker.check_all(
                drafts,
                state.facts,
                teams=state.teams,
                beat_kind=state.bundle["beat"]["kind"],
                beat_label=state.bundle["beat"]["label"],
                labels=state.labels,
                names=state.names,
            )

    @handler
    async def check(self, m: Drafted, ctx: WorkflowContext[Revise, BeatRun]) -> None:
        first = await asyncio.to_thread(self._check, m.state, m.drafts)
        failed, revision = self._checker.plan_retry(m.drafts, first)
        if revision is not None:
            await ctx.send_message(Revise(m, first, failed, revision))
            return
        await self._finish(m, first, [], {}, [], ctx)

    @handler
    async def recheck(self, m: Redrafted, ctx: WorkflowContext[Never, BeatRun]) -> None:
        r = m.revise
        revised = self._checker.accept_revisions(r.failed, r.revision, m.new)
        again = await asyncio.to_thread(
            self._check, r.drafted.state, list(revised.values())
        )
        await self._finish(
            r.drafted,
            r.first,
            r.failed,
            dict(zip(revised, again, strict=True)),
            m.calls,
            ctx,
        )

    async def _finish(
        self,
        drafted: Drafted,
        first: list[ClaimCheck],
        failed: list[int],
        redone: dict[int, ClaimCheck],
        retry_calls: list[Structured[Any]],
        ctx: WorkflowContext[Any, BeatRun],
    ) -> None:
        deps, state = self._deps, drafted.state
        checked = self._checker.settle(
            drafted.drafts,
            first,
            failed,
            redone,
            beat_id=state.job.beat_id,
            lang="en",
        )
        with _tracer.start_as_current_span("put_claims", context=state.job.ctx):
            claims = [stamp_trace(c.claim, state.job.ctx) for c in checked]
            written = tool_result(
                await deps.server.call_tool(
                    "put_claims",
                    {
                        "match_id": state.job.match_id,
                        "beat_id": state.job.beat_id,
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
        calls = [*drafted.calls, *retry_calls]
        run = BeatRun(
            claims=claims,
            checked=[
                CheckedClaim(c, k.first, k.final)
                for c, k in zip(claims, checked, strict=True)
            ],
            latency_ms=round((time.perf_counter() - state.started) * 1000),
            narrator_tokens=sum(c.input_tokens + c.output_tokens for c in calls),
            judge_tokens=sum(
                c.final.input_tokens
                + c.first.input_tokens
                + c.final.output_tokens
                + c.first.output_tokens
                for c in checked
            ),
            narrator_calls=calls,
            decision=state.decision,
        )
        await ctx.yield_output(run)


def stamp_trace(claim: Claim, parent: Context | None) -> Claim:
    """The claim with the trace id of the beat it belongs to, so a verdict can be found in the trace."""
    span = trace.get_current_span(parent)
    trace_id = span.get_span_context().trace_id
    if not trace_id or claim.checker is None:
        return claim
    checker = claim.checker.model_copy(update={"trace_id": f"{trace_id:032x}"})
    return claim.model_copy(update={"checker": checker})


def previews(beat_id: str, drafts: list[DraftClaim]) -> list[Claim]:
    """The drafts as claims still `checking`, with the ids the settled claims will have."""
    stem = beat_id.removeprefix("bt-")
    out: list[Claim] = []
    for i, d in enumerate(drafts):
        try:
            out.append(
                Claim.model_validate(
                    {
                        "id": f"cl-{stem}-{i + 1:02d}",
                        "beat_id": beat_id,
                        "lang": "en",
                        "text": d.text,
                        "fact_ids": d.fact_ids,
                        "numbers": [],
                        "verdict": "checking",
                    }
                )
            )
        except ValidationError:
            continue  # a draft that cannot be a claim is not shown while it is checked
    return out


def build_workflow(deps: Deps) -> Workflow:
    """Producer to Narrator to Checker, with the one conditional edge back from Checker to Narrator."""
    producer = ProducerExecutor(deps)
    narrator = NarratorExecutor(deps)
    checker = CheckerExecutor(deps)
    return (
        WorkflowBuilder(start_executor=producer)
        .add_edge(producer, narrator, condition=lambda m: isinstance(m, Briefed))
        .add_edge(
            narrator, checker, condition=lambda m: isinstance(m, Drafted | Redrafted)
        )
        .add_edge(checker, narrator, condition=lambda m: isinstance(m, Revise))
        .build()
    )


async def run_beat_workflow(
    match_id: str,
    beat_id: str,
    mode: Mode,
    *,
    deps: Deps,
    parent: Context | None = None,
    ticket: int | None = None,
    gate: TurnGate | None = None,
) -> BeatRun:
    """One beat through the workflow. Never raises for a model error: the run says what was lost."""
    with _tracer.start_as_current_span(
        "beat",
        context=parent,
        attributes={
            "gen_ai.operation.name": "invoke_workflow",
            "matchproof.match_id": match_id,
            "matchproof.beat_id": beat_id,
            "matchproof.mode": mode,
        },
    ) as span:
        job = BeatJob(match_id, beat_id, mode, ticket)
        _running[job.key] = (trace.set_span_in_context(span), gate)
        try:
            result = await build_workflow(deps).run(job)
        finally:
            del _running[job.key]
        outputs = result.get_outputs()
        if len(outputs) != 1 or not isinstance(outputs[0], BeatRun):
            raise RuntimeError(f"workflow for {beat_id} gave {len(outputs)} outputs")
        run: BeatRun = outputs[0]
        sc = span.get_span_context()
        run.trace_id, run.span_id = f"{sc.trace_id:032x}", f"{sc.span_id:016x}"
        span.set_attribute("matchproof.beat.latency_ms", run.latency_ms)
        span.set_attribute(
            "matchproof.verdicts", ",".join(c.verdict.value for c in run.claims)
        )
    if deps.observer is not None:
        deps.observer.settled(beat_id, run)
    return run
