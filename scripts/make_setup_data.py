"""Build apps/web/fixtures/setup.json: what the desk's setup bar needs from the simulator.

The browser computes no football, so the pieces it would otherwise work out come from here:
- storylines: each preset's id, text and planted beats, so choosing a storyline fills the brief;
- shapes: every formation's 11 slot positions for each side in absolute pitch coordinates, so the
  pre-match pitch can draw the brief's starting shape.
"""

import json
import sys
from pathlib import Path

from sim.brief import STORYLINES
from sim.tactics import FORMATIONS, slot_anchor

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "apps" / "web" / "fixtures" / "setup.json"


def build() -> dict[str, object]:
    return {
        "storylines": {
            story_id: {
                "text": story.text,
                "planted_beats": [
                    {
                        "id": f"pb-{i + 1:02d}",
                        "kind": kind,
                        "side": side,
                        "minute_from": lo,
                        "minute_to": hi,
                    }
                    for i, (kind, side, lo, hi) in enumerate(story.beats)
                ],
            }
            for story_id, story in STORYLINES.items()
        },
        "shapes": {
            formation: {
                side: [list(slot_anchor(formation, slot, side)) for slot in range(11)]
                for side in ("home", "away")
            }
            for formation in FORMATIONS
        },
    }


def main() -> int:
    out = DEFAULT_OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(build(), indent=1) + "\n")
    print(f"wrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
