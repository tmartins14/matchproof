"""The match store: everything the agents may ask about a match, in one place.

A running match is registered when its stream starts and filled in as the pipeline advances, so a
query mid-match sees only what has been computed so far. With an archive, a match that is not in
memory (evicted, or from before a restart) is loaded from it on first use; eviction applies to
memory only.
"""

import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Protocol

from contracts.models import Audit, Beat, Claim, Event, MatchBrief, PositionFrame
from intel.registry import FactRegistry

from .persist import ArchiveMissing, MatchArchive, load_record

MAX_MATCHES = 3  # matches held at once; the least recently used goes first


class UnknownMatch(KeyError):
    """No match with this id is in the store."""


@dataclass
class MatchRecord:
    brief: MatchBrief
    registry: FactRegistry
    events: list[Event] = field(default_factory=list)
    freeze_frames: dict[str, PositionFrame] = field(default_factory=dict)
    beats: list[Beat] = field(default_factory=list)
    claims: dict[str, list[Claim]] = field(default_factory=dict)
    finished: bool = False
    playback_t: float = 0.0  # match time last sent to viewers


class MatchStore(Protocol):
    """What the MCP server needs. Writers are for the pipeline; `put_claims` is for the agents."""

    def begin(self, brief: MatchBrief, registry: FactRegistry) -> None: ...

    def add_event(self, match_id: str, event: Event) -> None: ...

    def add_freeze_frame(
        self, match_id: str, event_id: str, frame: PositionFrame
    ) -> None: ...

    def add_beat(self, match_id: str, beat: Beat) -> None: ...

    def finish(self, match_id: str) -> None: ...

    def set_playback(self, match_id: str, t: float) -> None: ...

    def playback(self, match_id: str) -> float | None: ...

    def brief(self, match_id: str) -> MatchBrief: ...

    def registry(self, match_id: str) -> FactRegistry: ...

    def events(self, match_id: str) -> list[Event]: ...

    def freeze_frame(self, match_id: str, event_id: str) -> PositionFrame | None: ...

    def beats(self, match_id: str) -> list[Beat]: ...

    def put_claims(self, match_id: str, beat_id: str, claims: list[Claim]) -> None: ...

    def claims(self, match_id: str) -> dict[str, list[Claim]]: ...

    def put_audit(self, match_id: str, claim_id: str, audit: Audit) -> bool: ...

    def replace_claim(self, match_id: str, claim: Claim) -> bool: ...

    def last_playback(self, match_id: str) -> float: ...


class InMemoryMatchStore:
    """Matches by id, least recently used out first. Safe to share between the pipeline's worker
    thread and the event loop: every access takes the lock and hands back copies of the lists."""

    def __init__(
        self, max_matches: int = MAX_MATCHES, archive: MatchArchive | None = None
    ) -> None:
        self._max = max_matches
        self.archive = archive
        self._records: OrderedDict[str, MatchRecord] = OrderedDict()
        self._lock = threading.RLock()

    def _get(self, match_id: str) -> MatchRecord:
        """The record, marked as just used."""
        with self._lock:
            record = self._records.get(match_id)
            if record is None:
                record = self._load(match_id)
            self._records.move_to_end(match_id)
            return record

    def _load(self, match_id: str) -> MatchRecord:
        """Bring an archived match into memory (the lock is held)."""
        if self.archive is None:
            raise UnknownMatch(match_id)
        try:
            record = load_record(self.archive, match_id)
        except ArchiveMissing as exc:
            raise UnknownMatch(match_id) from exc
        self._records[match_id] = record
        while len(self._records) > self._max:
            self._records.popitem(last=False)
        return record

    def record(self, match_id: str) -> MatchRecord:
        """A copy of the match's record, safe to read while the pipeline keeps writing."""
        with self._lock:
            r = self._get(match_id)
            return MatchRecord(
                r.brief,
                r.registry,
                list(r.events),
                dict(r.freeze_frames),
                list(r.beats),
                {k: list(v) for k, v in r.claims.items()},
                r.finished,
                r.playback_t,
            )

    def begin(self, brief: MatchBrief, registry: FactRegistry) -> None:
        """Register a match, or start it afresh (a reconnect regenerates it); claims are kept."""
        match_id = brief.match_id
        with self._lock:
            old = self._records.get(match_id)
            record = MatchRecord(brief, registry)
            if old is not None:
                record.claims = old.claims
            self._records[match_id] = record
            self._records.move_to_end(match_id)
            while len(self._records) > self._max:
                self._records.popitem(last=False)

    def add_event(self, match_id: str, event: Event) -> None:
        with self._lock:
            self._get(match_id).events.append(event)

    def add_freeze_frame(
        self, match_id: str, event_id: str, frame: PositionFrame
    ) -> None:
        with self._lock:
            self._get(match_id).freeze_frames[event_id] = frame

    def add_beat(self, match_id: str, beat: Beat) -> None:
        with self._lock:
            self._get(match_id).beats.append(beat)

    def finish(self, match_id: str) -> None:
        with self._lock:
            self._get(match_id).finished = True

    def set_playback(self, match_id: str, t: float) -> None:
        """Record the match time last sent to viewers. It never moves back."""
        with self._lock:
            record = self._get(match_id)
            record.playback_t = max(record.playback_t, t)

    def playback(self, match_id: str) -> float | None:
        """The match time viewers have reached, or None once the match is finished and
        everything may be shown."""
        with self._lock:
            record = self._get(match_id)
            return None if record.finished else record.playback_t

    def brief(self, match_id: str) -> MatchBrief:
        with self._lock:
            return self._get(match_id).brief

    def registry(self, match_id: str) -> FactRegistry:
        with self._lock:
            return self._get(match_id).registry

    def events(self, match_id: str) -> list[Event]:
        with self._lock:
            return list(self._get(match_id).events)

    def freeze_frame(self, match_id: str, event_id: str) -> PositionFrame | None:
        with self._lock:
            return self._get(match_id).freeze_frames.get(event_id)

    def beats(self, match_id: str) -> list[Beat]:
        with self._lock:
            return list(self._get(match_id).beats)

    def put_claims(self, match_id: str, beat_id: str, claims: list[Claim]) -> None:
        with self._lock:
            self._get(match_id).claims.setdefault(beat_id, []).extend(claims)

    def claims(self, match_id: str) -> dict[str, list[Claim]]:
        with self._lock:
            return {k: list(v) for k, v in self._get(match_id).claims.items()}

    def put_audit(self, match_id: str, claim_id: str, audit: Audit) -> bool:
        """Attach an audit to a stored claim. False if the claim is not there."""
        with self._lock:
            for claims in self._get(match_id).claims.values():
                for i, claim in enumerate(claims):
                    if claim.id.root == claim_id:
                        claims[i] = claim.model_copy(update={"audit": audit})
                        return True
            return False

    def replace_claim(self, match_id: str, claim: Claim) -> bool:
        """Swap a stored claim for its corrected version (same id). False if it is not there."""
        with self._lock:
            claims = self._get(match_id).claims.get(claim.beat_id.root, [])
            for i, old in enumerate(claims):
                if old.id.root == claim.id.root:
                    claims[i] = claim
                    return True
            return False

    def last_playback(self, match_id: str) -> float:
        """The match time viewers last reached, kept after full time too."""
        with self._lock:
            return self._get(match_id).playback_t

    def __contains__(self, match_id: str) -> bool:
        with self._lock:
            return match_id in self._records
