"""Generated matches shared by the intel tests.

Two ways in, by what a test needs:
- match() holds every 5 Hz frame and freeze frame as model objects, for the tests that compare the
  streaming and batch paths. Two are kept at most; each is large.
- lean() runs the match straight through the fact engine and beat detector as it is generated and
  keeps only the events, beats and registry. Use it for everything that does not need the frames.

Both read the generator's output from .cache/matches/<key>/stream.jsonl when it is there (about a
third of the time of generating it) and write it there when it is not. The key is the brief's JSON
plus a hash of packages/sim/src, so a change to the generator makes a new entry. Entries are written
whole and renamed into place, so parallel test workers can share the folder.
"""

import gc
import hashlib
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from contracts.models import Beat, Event, MatchBrief, PositionFrame
from intel.beats import BeatDetector, merge_stream
from intel.engine import FactEngine
from intel.registry import FactRegistry
from sim import generate
from sim.brief import DEFAULT_AWAY, DEFAULT_HOME, make_brief
from sim.positions import run

ROOT = Path(__file__).resolve().parents[3]
CACHE_DIR = ROOT / ".cache" / "matches"
SIM_SRC = ROOT / "packages" / "sim" / "src"
STREAM_FILE = "stream.jsonl"
TAGS = {
    "event": "e",
    "frame": "f",
    "freeze": "z",
}  # one letter and a tab start each line

KEPT_MATCHES = 2  # matches held at once; the rest are rebuilt on demand


@contextmanager
def gc_paused() -> Iterator[None]:
    """Holding tens of thousands of frame models makes the cyclic collector crawl; pause it."""
    gc.disable()
    try:
        yield
    finally:
        gc.enable()


@dataclass
class Match:
    events: list[Event]
    frames: list[PositionFrame] = field(default_factory=list)
    freeze: list[PositionFrame] = field(default_factory=list)

    @property
    def stream(self) -> list[Event | PositionFrame]:
        """Events, freeze frames and frames in the order the generator yields them."""
        return merge_stream(self.events, self.frames, self.freeze)


@lru_cache(maxsize=1)
def sim_hash() -> str:
    """A hash of every file under packages/sim/src: what the generator is."""
    h = hashlib.sha256()
    for path in sorted(SIM_SRC.rglob("*.py")):
        h.update(str(path.relative_to(SIM_SRC)).encode())
        h.update(path.read_bytes())
    return h.hexdigest()


def cache_key(brief: MatchBrief) -> str:
    """The brief's JSON plus the generator's hash, so changing either makes a new entry."""
    h = hashlib.sha256(brief.model_dump_json(by_alias=True).encode())
    h.update(sim_hash().encode())
    return h.hexdigest()[:24]


def stream_path(brief: MatchBrief) -> Path:
    return CACHE_DIR / cache_key(brief) / STREAM_FILE


def write_stream(brief: MatchBrief) -> Path:
    """Generate the match and save its events, frames and freeze frames in the order run() yields them."""
    path = stream_path(brief)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{STREAM_FILE}.tmp-{os.getpid()}")
    with tmp.open("w", encoding="utf-8") as fh:
        for kind, event, frame in run(brief, generate(brief)):
            model = event if kind == "event" else frame
            if model is not None:
                body = model.model_dump_json(by_alias=True, exclude_none=True)
                fh.write(f"{TAGS[kind]}\t{body}\n")
    os.replace(
        tmp, path
    )  # whole or not at all, so another worker never reads half a file
    return path


def read_stream(brief: MatchBrief) -> Iterator[tuple[str, Event | PositionFrame]]:
    """The saved match one item at a time, generating and saving it first if it is not there."""
    path = stream_path(brief)
    if not path.exists():
        write_stream(brief)
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            tag, _, body = line.partition("\t")
            if tag == "e":
                yield "event", Event.model_validate_json(body)
            else:
                yield (
                    "frame" if tag == "f" else "freeze",
                    PositionFrame.model_validate_json(body),
                )


@lru_cache(maxsize=KEPT_MATCHES)
def match(story: str, seed: int) -> Match:
    brief = make_brief(DEFAULT_HOME, DEFAULT_AWAY, story, seed)
    m = Match([])
    with gc_paused():
        for kind, item in read_stream(brief):
            if isinstance(item, Event):
                m.events.append(item)
            else:
                (m.frames if kind == "frame" else m.freeze).append(item)
    return m


@dataclass
class Lean:
    events: list[Event]
    beats: list[Beat]
    registry: FactRegistry


def compute_lean(story: str, seed: int) -> Lean:
    """The live path, minus the wire: no frame is kept once the engine and detector have seen it."""
    brief = make_brief(DEFAULT_HOME, DEFAULT_AWAY, story, seed)
    events: list[Event] = []
    engine, detector = FactEngine(), BeatDetector()
    beats: list[Beat] = []
    for _, item in read_stream(brief):
        if isinstance(item, Event):
            events.append(item)
        engine.push(item)
        beats += detector.push(item, engine.registry)
    engine.finish()
    beats += detector.finish(engine.registry)
    return Lean(events, beats, engine.registry)


@lru_cache(maxsize=KEPT_MATCHES)
def lean(story: str, seed: int) -> Lean:
    return compute_lean(story, seed)
