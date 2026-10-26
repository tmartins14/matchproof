"""Record apps/web/public/trials/streams/<fixture>.ndjson.gz, the streams the Desk replays cached.

Each pack fixture's brief (the one the trials runner builds) is played through the real run_live
with no agents, the whole match, at speed 6. A VirtualPacer stands in for the clock: sleeping sets
the virtual time and never waits, so a recording takes seconds but every message keeps the offset
(`wall_ms`, from the first message) the live path would have sent it at, focus windows and freeze
holds included. One `{"wall_ms": n, "msg": <StreamMessage>}` per line, gzipped with no timestamp so a
second recording gives identical bytes. Frames are thinned the way record_stream.py does; a file over
MAX_GZ_BYTES gets the wider fallback gap.
"""

import argparse
import asyncio
import gzip
import json
import sys
from pathlib import Path

from api.live import run_live
from contracts.models import StreamMessage

from evals.trials import PACK_PATH, Fixture, load_pack
from scripts.record_stream import FALLBACK_GAP_S, FRAME_GAP_S, MAX_GZ_BYTES, thin

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIR = ROOT / "apps" / "web" / "public" / "trials" / "streams"
SPEED = 6


class VirtualPacer:
    """A clock that jumps: `sleep_until(t)` sets it to max(now, t) and returns at once."""

    def __init__(self) -> None:
        self._now = 0.0

    def now(self) -> float:
        return self._now

    async def sleep_until(self, real_t: float) -> None:
        self._now = max(self._now, real_t)


async def play(fixture: Fixture) -> list[tuple[int, StreamMessage]]:
    """The whole match with the virtual wall offset, in ms, each message was sent at."""
    pacer = VirtualPacer()
    return [
        (round(pacer.now() * 1000), m)
        async for m in run_live(fixture.make_brief(), SPEED, pacer=pacer)
    ]


def thin_timed(
    played: list[tuple[int, StreamMessage]], gap_s: float
) -> list[tuple[int, StreamMessage]]:
    """`thin`, keeping each message's offset. The kept messages are matched back by seq."""
    kept = {m.seq for m in thin([m for _, m in played], gap_s)}
    return [(ms, m) for ms, m in played if m.seq in kept]


def encode(timed: list[tuple[int, StreamMessage]]) -> bytes:
    raw = "".join(
        json.dumps(
            {
                "wall_ms": ms,
                "msg": json.loads(m.model_dump_json(by_alias=True, exclude_none=True)),
            },
            separators=(",", ":"),
        )
        + "\n"
        for ms, m in timed
    ).encode()
    return gzip.compress(raw, compresslevel=9, mtime=0)


def record(fixture: Fixture) -> tuple[bytes, int, float]:
    """The gzipped recording, its message count and the frame gap used outside focus windows."""
    played = asyncio.run(play(fixture))
    gap = FRAME_GAP_S
    packed = encode(thin_timed(played, gap))
    if len(packed) > MAX_GZ_BYTES:
        gap = FALLBACK_GAP_S
        packed = encode(thin_timed(played, gap))
    return packed, len(thin_timed(played, gap)), gap


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_DIR)
    parser.add_argument("--pack", type=Path, default=PACK_PATH)
    parser.add_argument("--fixture", action="append", help="only these fixture ids")
    args = parser.parse_args()

    _, fixtures = load_pack(args.pack)
    args.out.mkdir(parents=True, exist_ok=True)
    over = 0
    for fixture in fixtures:
        if args.fixture and fixture.id not in args.fixture:
            continue
        packed, count, gap = record(fixture)
        path = args.out / f"{fixture.id}.ndjson.gz"
        path.write_bytes(packed)
        print(
            f"{fixture.id}: {count} messages, frame gap {gap:.0f} s, {len(packed)} bytes gzipped"
        )
        over += len(packed) > MAX_GZ_BYTES
    return 1 if over else 0


if __name__ == "__main__":
    sys.exit(main())
