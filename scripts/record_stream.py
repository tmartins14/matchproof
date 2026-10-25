"""Record apps/web/fixtures/stream-short.ndjson.gz, the stream the desk tests replay.

Plays red_card_flip seed 3 through the real run_live with a no-op pacer and no agents, up to
RED_CARD_S + AFTER_RED_CARD_S, and writes one stream message per line, gzipped with no timestamp so
a second recording gives identical bytes. Everything is kept except frames: a frame stays if it is a
freeze frame, falls inside a focus window, or is the first one at least FRAME_GAP_S after the last
kept. If the file is over MAX_GZ_BYTES, FRAME_GAP_S rises to FALLBACK_GAP_S for the frames outside
focus windows. Seq numbers are the stream's own, so thinning leaves gaps.
"""

import argparse
import asyncio
import gzip
import json
import sys
from collections import Counter
from pathlib import Path

from api.live import NoPacer, run_live
from contracts.models import StreamMessage
from sim.brief import make_brief

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "apps" / "web" / "fixtures" / "stream-short.ndjson.gz"
STORYLINE = "red_card_flip"
SEED = 3
SPEED = 6
RED_CARD_S = 3771.19  # ev-001479; the stream is cut 25 match minutes after it
AFTER_RED_CARD_S = 1500.0
FRAME_GAP_S = 10.0
FALLBACK_GAP_S = 30.0
MAX_GZ_BYTES = 1024 * 1024


async def play() -> list[StreamMessage]:
    brief = make_brief(storyline_id=STORYLINE, seed=SEED)
    return [
        m
        async for m in run_live(
            brief, SPEED, pacer=NoPacer(), until_s=RED_CARD_S + AFTER_RED_CARD_S
        )
    ]


def thin(messages: list[StreamMessage], gap_s: float) -> list[StreamMessage]:
    kept: list[StreamMessage] = []
    in_focus = False
    after_freeze = False
    last_kept_t = -gap_s
    for m in messages:
        if m.type.value == "status":
            state = m.data.state.value  # type: ignore[union-attr]
            if state == "focus":
                in_focus = True
            elif state in ("live", "half_time", "full_time"):
                in_focus = False
            after_freeze = state == "freeze"
        elif m.type.value == "frame":
            t = m.t.root
            keep = after_freeze or in_focus or t - last_kept_t >= gap_s
            after_freeze = False
            if not keep:
                continue
            if not in_focus:
                last_kept_t = t
        kept.append(m)
    return kept


def encode(messages: list[StreamMessage]) -> tuple[bytes, bytes]:
    raw = "".join(
        m.model_dump_json(by_alias=True, exclude_none=True) + "\n" for m in messages
    ).encode()
    return raw, gzip.compress(raw, compresslevel=9, mtime=0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    played = asyncio.run(play())
    gap = FRAME_GAP_S
    raw, packed = encode(thin(played, gap))
    if len(packed) > MAX_GZ_BYTES:
        gap = FALLBACK_GAP_S
        raw, packed = encode(thin(played, gap))
    kept = thin(played, gap)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(packed)

    counts = Counter(m.type.value for m in kept)
    played_counts = Counter(m.type.value for m in played)
    print(f"played {len(played)} messages {dict(played_counts)}")
    print(
        f"kept {len(kept)} messages {dict(counts)}, frame gap {gap:.0f} s outside focus"
    )
    print(
        f"raw {len(raw)} bytes, gzipped {len(packed)} bytes: {args.out.relative_to(ROOT)}"
    )
    if len(packed) > MAX_GZ_BYTES:
        print(f"over {MAX_GZ_BYTES} bytes gzipped", file=sys.stderr)
        return 1
    last = json.loads(raw.splitlines()[-1])
    print(
        f"last message: {last['type']} {last['data'].get('state')} {last['data'].get('score')}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
