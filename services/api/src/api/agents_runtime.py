"""The agent workflow as the live stream uses it: one MatchRun per match, built on the process-wide
runtime.

A MatchRun takes each beat as the detector finds it (in the lookahead), runs it through the
workflow on a bounded pool, and keeps what the player needs when playback reaches the beat: the
Producer's decision, the drafts while they are checked, and the settled claims. Audits run after the
Checker settles a claim, on their own bounded pool, and never hold anything up.

Verify before air: the pipeline runs ahead of playback, so a beat's claims are usually settled before
the viewer gets there. The player sends whatever state is true at that moment and the rest as it
lands; nothing here waits for a clock.
"""

import asyncio
import json
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from agents.auditor import MAX_CONCURRENT_AUDITS, Auditor
from agents.budget import MeteredClient, budget
from agents.llm_client import ChatClient
from agents.pipeline import BeatRun, Deps, ToolServer
from agents.producer import Decision, Producer
from agents.workflow import TurnGate, run_beat_workflow
from contracts.models import Audit, Beat, Claim, MatchBrief
from mcp.client.session import ClientSession
from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.trace import Span, SpanContext

MAX_CONCURRENT_BEATS = 3
MAX_RUNS = 6  # matches whose agent state is kept for reconnects
SETTLED = ("verified", "rephrased")


class SessionServer:
    """The internal MCP server through an in-process client session: the agents' only way to the
    match. Nothing here listens on a network."""

    def __init__(self, session: ClientSession) -> None:
        self._session = session

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        result = await self._session.call_tool(name, arguments)
        if result.isError:
            text = " ".join(getattr(c, "text", "") for c in result.content)
            raise ValueError(f"{name}: {text}")
        if isinstance(result.structuredContent, dict):
            return result.structuredContent
        parsed: dict[str, Any] = json.loads(result.content[0].text)  # type: ignore[union-attr]
        return parsed


@dataclass
class BeatTrack:
    """Where one beat is in the workflow, as futures the player can wait on."""

    decided: "asyncio.Future[Decision | None]"
    drafted: "asyncio.Future[list[Claim]]"
    done: "asyncio.Future[BeatRun]"


@dataclass
class AuditLedger:
    audited: list[tuple[Claim, Audit, str]] = field(default_factory=list)
    skipped: int = 0
    pending: int = 0


class MatchRun:
    """The agents' state for one match. Lives on the event loop."""

    def __init__(self, runtime: "AgentRuntime", brief: MatchBrief) -> None:
        self.match_id = brief.match_id
        self._runtime = runtime
        self.producer = Producer(runtime.producer_client)
        self._tracks: dict[str, BeatTrack] = {}
        self._claims: dict[str, list[Claim]] = {}
        self._reasons: dict[str, str] = {}  # claim id to what the inline judge said
        self._beats = asyncio.Semaphore(MAX_CONCURRENT_BEATS)
        self._audits = asyncio.Semaphore(MAX_CONCURRENT_AUDITS)
        self._gate = TurnGate()
        self._tickets = 0
        self._tasks: set[asyncio.Task[Any]] = set()
        self._listeners: list[Callable[[Claim, str | None], None]] = []
        self._spans: dict[str, str] = {}
        self.ledger = AuditLedger()
        self.down = False
        self.span: Span = runtime.tracer.start_span(
            "match", attributes={"matchproof.match_id": self.match_id}
        )
        self.context: Context = trace.set_span_in_context(self.span)
        self.deps = Deps(
            runtime.server,
            runtime.narrator,
            runtime.judge,
            producer=self.producer,
            observer=self,
            paused=lambda: budget.narration_paused,
        )

    # ---- feeding the workflow ----------------------------------------------------------------
    def submit(self, beat: Beat) -> None:
        """Take a beat the detector has just found. Does nothing for one already taken."""
        beat_id = beat.id.root
        if beat_id in self._tracks:
            return
        loop = asyncio.get_running_loop()
        self._tracks[beat_id] = BeatTrack(
            loop.create_future(), loop.create_future(), loop.create_future()
        )
        ticket, self._tickets = self._tickets, self._tickets + 1
        self._spawn(self._run_beat(beat_id, ticket))

    def _spawn(self, coro: Any) -> None:
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run_beat(self, beat_id: str, ticket: int) -> None:
        track = self._tracks[beat_id]
        try:
            async with self._beats:
                await run_beat_workflow(
                    self.match_id,
                    beat_id,
                    "fan",
                    deps=self.deps,
                    parent=self.context,
                    ticket=ticket,
                    gate=self._gate,
                )
        except Exception as exc:  # noqa: BLE001 - a task boundary: the match keeps playing without agents
            self.down = True
            self.settled(
                beat_id, BeatRun([], [], 0, error=f"workflow: {type(exc).__name__}")
            )
        finally:
            await self._gate.release(
                ticket
            )  # a beat that died before deciding must not stall the rest
            if not track.decided.done():
                track.decided.set_result(None)

    # ---- the workflow's observer ---------------------------------------------------------------
    def decided(self, beat_id: str, decision: Decision) -> None:
        track = self._tracks[beat_id]
        if not track.decided.done():
            track.decided.set_result(decision)

    def drafted(self, beat_id: str, previews: list[Claim]) -> None:
        track = self._tracks[beat_id]
        if not track.drafted.done():
            track.drafted.set_result(previews)

    def settled(self, beat_id: str, run: BeatRun) -> None:
        track = self._tracks[beat_id]
        if track.done.done():
            return
        self._claims[beat_id] = list(run.claims)
        if run.span_id:
            self._spans[beat_id] = run.span_id
        for c in run.checked:
            self._reasons[c.claim.id.root] = c.final.judge_reason
        track.done.set_result(run)
        for claim in run.claims:
            if claim.verdict.value in SETTLED:
                self._spawn(self._audit(claim, run))

    # ---- what the player asks ------------------------------------------------------------------
    def track(self, beat_id: str) -> BeatTrack | None:
        return self._tracks.get(beat_id)

    async def decision(self, beat_id: str, timeout_s: float) -> Decision | None:
        """The Producer's decision for a beat, or None if the workflow has none in time."""
        track = self._tracks.get(beat_id)
        if track is None:
            return None
        try:
            return await asyncio.wait_for(asyncio.shield(track.decided), timeout_s)
        except TimeoutError:
            return None

    def claims_now(self, beat_id: str) -> list[Claim]:
        return list(self._claims.get(beat_id, []))

    def span_id(self, beat_id: str) -> str | None:
        return self._spans.get(beat_id)

    def subscribe(
        self, listener: Callable[[Claim, str | None], None]
    ) -> Callable[[], None]:
        """Be told when a claim gets its audit. Returns the unsubscribe."""
        self._listeners.append(listener)
        return lambda: (
            self._listeners.remove(listener) if listener in self._listeners else None
        )

    async def drain(self, timeout_s: float) -> None:
        """Wait for the beats still in the workflow (not the audits)."""
        pending = [t.done for t in self._tracks.values() if not t.done.done()]
        if pending:
            await asyncio.wait(pending, timeout=timeout_s)

    # ---- the auditor ---------------------------------------------------------------------------
    async def _audit(self, claim: Claim, run: BeatRun) -> None:
        auditor = self._runtime.auditor
        if auditor is None:
            return
        if budget.auditing_stopped:  # auditing goes first when the day's tokens run low
            self.ledger.skipped += 1
            return
        self.ledger.pending += 1
        try:
            async with self._audits:
                link: SpanContext | None = None
                if run.span_id and run.trace_id:
                    link = SpanContext(
                        int(run.trace_id, 16),
                        int(run.span_id, 16),
                        is_remote=False,
                    )
                result = await auditor.audit(
                    self.match_id, claim, parent=self.context, link=link
                )
        except Exception as exc:  # noqa: BLE001 - log-only: an audit that breaks must not touch the match
            self.producer.note_audit(
                f"The second model could not be reached for {claim.id.root}: {type(exc).__name__}."
            )
            return
        finally:
            self.ledger.pending -= 1
        reason = self._reasons.get(claim.id.root, "")
        self.ledger.audited.append((claim, result, reason))
        audited = claim.model_copy(update={"audit": result})
        self._claims[claim.beat_id.root] = [
            audited if c.id.root == claim.id.root else c
            for c in self._claims.get(claim.beat_id.root, [])
        ]
        if result.outcome.value == "disagree":
            self.producer.note_audit(
                f"The second model disagrees on {claim.id.root} ({result.problem}): {result.reason}"
            )
        for listener in list(self._listeners):
            listener(audited, self._spans.get(claim.beat_id.root))

    def audit_summary(self) -> dict[str, Any]:
        done = self.ledger.audited
        agreed = sum(1 for _, a, _ in done if a.outcome.value == "agree")
        disagreed = [(c, a, r) for c, a, r in done if a.outcome.value == "disagree"]
        unavailable = sum(1 for _, a, _ in done if a.outcome.value == "unavailable")
        audited = agreed + len(disagreed)
        return {
            "match_id": self.match_id,
            "claims_audited": audited,
            "agreement_rate": round(agreed / audited, 3) if audited else None,
            "disagreements": [
                {
                    "claim_id": c.id.root,
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
            "unavailable": unavailable,
            "skipped_for_token_cap": self.ledger.skipped,
            "pending": self.ledger.pending,
        }

    def producer_log(self) -> list[dict[str, Any]]:
        return list(self.producer.log)

    def close(self) -> None:
        if self.span.is_recording():
            self.span.end()


class AgentRuntime:
    """The model clients and the MCP session, shared by every match the process streams."""

    def __init__(
        self,
        server: ToolServer,
        *,
        narrator: ChatClient,
        judge: ChatClient,
        producer: ChatClient,
        auditor: ChatClient | None,
    ) -> None:
        self.server = server
        self.narrator: ChatClient = MeteredClient(narrator, "narrator")
        self.judge: ChatClient = MeteredClient(judge, "judge")
        self.producer_client: ChatClient = MeteredClient(producer, "producer")
        self.auditor = (
            Auditor(MeteredClient(auditor, "auditor"), server) if auditor else None
        )
        self.tracer = trace.get_tracer("matchproof.match")
        self._runs: OrderedDict[str, MatchRun] = OrderedDict()

    def match(self, brief: MatchBrief) -> MatchRun:
        """The agents' run for a match; a reconnect to the same match gets the same one."""
        run = self._runs.get(brief.match_id)
        if run is None:
            run = MatchRun(self, brief)
            self._runs[brief.match_id] = run
            while len(self._runs) > MAX_RUNS:
                self._runs.popitem(last=False)[1].close()
        self._runs.move_to_end(brief.match_id)
        return run

    def existing(self, match_id: str) -> MatchRun | None:
        return self._runs.get(match_id)


class DownRun:
    """Stands in for a MatchRun when the agent workflow could not be started: beats stream without
    claims and the stream says verification is unavailable."""

    down = True

    def submit(self, beat: Beat) -> None:
        return None

    def track(self, beat_id: str) -> BeatTrack | None:
        return None

    async def decision(self, beat_id: str, timeout_s: float) -> Decision | None:
        return None

    def span_id(self, beat_id: str) -> str | None:
        return None

    def claims_now(self, beat_id: str) -> list[Claim]:
        return []

    def subscribe(
        self, listener: Callable[[Claim, str | None], None]
    ) -> Callable[[], None]:
        return lambda: None
