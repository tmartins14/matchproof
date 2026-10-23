"""Saving a finished match to the archive, off the stream's path.

The stream calls `schedule_save` when it reaches full time. The save runs as a background task, waits
a little for the second model's audits to land, then writes the match. A match that is already
archived is left as it is, and a failed save is logged and dropped: the stream has already ended.
"""

import asyncio
import gc
import logging
import os
from datetime import UTC, datetime
from typing import Any

from agents.budget import budget
from azure.core.exceptions import AzureError
from contracts.models import MatchBrief
from mcp_match import ArchiveMissing, InMemoryMatchStore
from mcp_match.persist import MANIFEST, save_match
from pydantic import ValidationError
from sim.positions import iter_frames

from api.agents_runtime import MatchRun

AUDIT_WAIT_S = 60.0  # how long a save waits for audits still running
AUDIT_POLL_S = 0.5
log = logging.getLogger(__name__)
_tasks: set["asyncio.Task[None]"] = set()  # strong references until each save is done


def git_sha() -> str:
    return os.environ.get("GIT_SHA", "unknown")


def schedule_save(
    store: InMemoryMatchStore, brief: MatchBrief, run: object | None
) -> None:
    """Start saving the match in the background. Needs a running event loop."""
    if store.archive is None:
        return
    task = asyncio.ensure_future(save_when_settled(store, brief, run))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def save_when_settled(
    store: InMemoryMatchStore, brief: MatchBrief, run: object | None
) -> None:
    waited = 0.0
    while (
        isinstance(run, MatchRun) and run.ledger.pending > 0 and waited < AUDIT_WAIT_S
    ):
        await asyncio.sleep(AUDIT_POLL_S)
        waited += AUDIT_POLL_S
    audit: dict[str, Any] = run.audit_summary() if isinstance(run, MatchRun) else {}
    producer_log = run.producer_log() if isinstance(run, MatchRun) else []
    try:
        await asyncio.to_thread(
            save_now,
            store,
            brief,
            audit,
            producer_log,
            budget.match_usage(brief.match_id),
        )
    except (OSError, AzureError, ValidationError, KeyError, RuntimeError) as exc:
        log.warning(
            "could not archive %s: %s: %s", brief.match_id, type(exc).__name__, exc
        )


def save_now(
    store: InMemoryMatchStore,
    brief: MatchBrief,
    audit: dict[str, Any],
    producer_log: list[dict[str, Any]],
    usage: dict[str, Any],
) -> bool:
    """Write the match unless it is already there. True if it wrote."""
    archive = store.archive
    assert archive is not None
    try:
        archive.get(brief.match_id, MANIFEST)
        return False
    except ArchiveMissing:
        pass
    record = store.record(brief.match_id)
    # Frames are regenerated, not held: the same brief and events always give the same frames.
    gc.disable()  # tens of thousands of frame models; the cyclic collector would crawl over them
    try:
        save_match(
            archive,
            record,
            frames=iter_frames(brief, record.events),
            audit=audit,
            producer_log=producer_log,
            usage=usage,
            git_sha=git_sha(),
            created_at=datetime.now(UTC),
        )
    finally:
        gc.enable()
    return True
