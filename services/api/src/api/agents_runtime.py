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

from agents.auditor import MAX_CONCURRENT_AUDITS, Auditor, summarize_audits
from agents.budget import MeteredClient, budget, current_match
from agents.consensus import Consensus
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
    corrections: list[Claim] = field(
        default_factory=list
    )  # corrected or blocked, as now stored
    unresolved: list[tuple[Claim, str]] = field(
        default_factory=list
    )  # claim, judge on re-check
    skipped: int = 0
    pending: int = 0


class MatchRun:
    """The agents' state for one match. Lives on the event loop."""

    def __init__(
        self,
        runtime: "AgentRuntime",
        brief: MatchBrief,
        narrator_id: str | None = None,
        narrator: ChatClient | None = None,
    ) -> None:
        self.match_id = brief.match_id
        self.narrator_id = narrator_id  # None: the process-wide Narrator
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
        self._correction_listeners: list[Callable[[Claim, str | None], None]] = []
        self._corrected: set[str] = (
            set()
        )  # claims already reviewed: one correction at most
        self._spans: dict[str, str] = {}
        self.ledger = AuditLedger()
        self.down = False
        self.span: Span = runtime.tracer.start_span(
            "match",
            attributes={
                "matchproof.match_id": self.match_id,
                **({"matchproof.narrator": narrator_id} if narrator_id else {}),
            },
        )
        self.context: Context = trace.set_span_in_context(self.span)
        self.deps = Deps(
            runtime.server,
            narrator or runtime.narrator,
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
        token = current_match.set(
            self.match_id
        )  # the task copies this; calls inside are ours
        try:
            task = asyncio.ensure_future(coro)
        finally:
            current_match.reset(token)
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

    async def quiesce(self) -> None:
        """Wait until every beat taken so far has settled. Tests use it to hold playback still."""
        pending: list[asyncio.Future[BeatRun]] = [
            t.done for t in self._tracks.values() if not t.done.done()
        ]
        if pending:
            await asyncio.wait(pending)

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

    def subscribe_corrections(
        self, listener: Callable[[Claim, str | None], None]
    ) -> Callable[[], None]:
        """Be told when a claim is corrected or blocked by consensus. Returns the unsubscribe."""
        self._correction_listeners.append(listener)
        return lambda: (
            self._correction_listeners.remove(listener)
            if listener in self._correction_listeners
            else None
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
        if result.outcome.value == "disagree" and claim.verdict.value in SETTLED:
            await self._correct(claim, result)

    # ---- corrections by consensus --------------------------------------------------------------
    async def _correct(self, claim: Claim, audit: Audit) -> None:
        """Ask the inline judge again; if it agrees with the auditor, rewrite or block the claim."""
        consensus = self._runtime.consensus
        claim_id = claim.id.root
        if consensus is None or claim_id in self._corrected or budget.auditing_stopped:
            return
        self._corrected.add(claim_id)
        self.ledger.pending += 1
        try:
            at_t = self._runtime.clock(self.match_id)
            outcome = await consensus.review(self.match_id, claim, audit, at_t)
            if outcome.kind == "unresolved" or outcome.claim is None:
                self.ledger.unresolved.append((claim, outcome.recheck_reason))
                self.producer.note_audit(outcome.note)
                return
            try:
                await self._runtime.server.call_tool(
                    "put_correction",
                    {
                        "match_id": self.match_id,
                        "claim": outcome.claim.model_dump(
                            mode="json", by_alias=True, exclude_none=True
                        ),
                    },
                )
            except (OSError, ValueError) as exc:
                self.producer.note_audit(
                    f"{claim_id} could not be corrected: {type(exc).__name__}."
                )
                return
            beat_id = claim.beat_id.root
            self._claims[beat_id] = [
                outcome.claim if c.id.root == claim_id else c
                for c in self._claims.get(beat_id, [])
            ]
            self.ledger.corrections.append(outcome.claim)
            self.producer.note_audit(outcome.note)
            for listener in list(self._correction_listeners):
                listener(outcome.claim, self._spans.get(beat_id))
        finally:
            self.ledger.pending -= 1

    def audit_summary(self) -> dict[str, Any]:
        return {
            **summarize_audits(
                self.match_id,
                self.ledger.audited,
                self.ledger.corrections,
                self.ledger.unresolved,
            ),
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
        clock: Callable[[str], float] = lambda _: 0.0,
        narrator_for: Callable[[str], ChatClient] | None = None,
    ) -> None:
        self.server = server
        self._narrator_for = narrator_for  # a live-ready candidate id to its own client
        self.clock = (
            clock  # match time viewers have reached, for the time of a correction
        )
        self.narrator: ChatClient = MeteredClient(narrator, "narrator")
        self.judge: ChatClient = MeteredClient(judge, "judge")
        self.producer_client: ChatClient = MeteredClient(producer, "producer")
        self.auditor = (
            Auditor(MeteredClient(auditor, "auditor"), server) if auditor else None
        )
        self.consensus = (
            Consensus(self.judge, self.narrator, server)
            if auditor is not None
            else None
        )
        self.tracer = trace.get_tracer("matchproof.match")
        self._runs: OrderedDict[str, MatchRun] = OrderedDict()

    def match(self, brief: MatchBrief, narrator_id: str | None = None) -> MatchRun:
        """The agents' run for a match; a reconnect to the same match gets the same one. With
        `narrator_id` the match's Narrator is its own client; the referee stays shared."""
        run = self._runs.get(brief.match_id)
        if run is None:
            client = None
            if narrator_id is not None:
                if self._narrator_for is None:
                    raise ValueError("no per-match narrators are configured")
                client = MeteredClient(self._narrator_for(narrator_id), "narrator")
            run = MatchRun(self, brief, narrator_id, client)
            self._runs[brief.match_id] = run
            while len(self._runs) > MAX_RUNS:
                self._runs.popitem(last=False)[1].close()
        self._runs.move_to_end(brief.match_id)
        return run

    def existing(self, match_id: str) -> MatchRun | None:
        return self._runs.get(match_id)

    def pending_audits(self) -> int:
        return sum(run.ledger.pending for run in list(self._runs.values()))


class DownRun:
    """Stands in for a MatchRun when the agent workflow could not be started: beats stream without
    claims and the stream says verification is unavailable."""

    down = True

    def close(self) -> None:
        return None

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

    def subscribe_corrections(
        self, listener: Callable[[Claim, str | None], None]
    ) -> Callable[[], None]:
        return lambda: None
