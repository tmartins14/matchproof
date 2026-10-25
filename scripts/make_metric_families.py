"""Build apps/web/fixtures/metric-families.json: one real fact of every metric family the registry emits.

The desk names a fact's metric from copy by the name without its arguments (`compactness_change`,
`sequence.seconds`). This file lets a test check that every family has copy in both languages and
render the stat card for each one. The facts come from full registries of three storylines, with the
desk label written the way the stream writes it.
"""

import json
import re
import sys
from pathlib import Path
from typing import Any

from api.live import roster_of, teams_of
from intel.beats import detect_all
from intel.engine import extract_all
from intel.labels import LabelContext, desk_label_for
from sim import generate
from sim.brief import make_brief
from sim.positions import iter_frames, iter_freeze_frames

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "apps" / "web" / "fixtures" / "metric-families.json"
MATCHES = (("red_card_flip", 3), ("end_to_end", 2), ("late_comeback", 1))


def family_of(name: str) -> str:
    return re.sub(r"\([^)]*\)", "", name)


def build() -> list[dict[str, Any]]:
    by_family: dict[str, dict[str, Any]] = {}
    for story, seed in MATCHES:
        brief = make_brief(storyline_id=story, seed=seed)
        events = generate(brief)
        frames = list(iter_frames(brief, events))
        freeze = list(iter_freeze_frames(brief, events))
        registry = extract_all(
            events, frames, freeze, roster_of(brief), teams_of(brief)
        )
        detect_all(events, frames, freeze, registry)
        ctx = LabelContext(teams_of(brief), {e.id.root: e for e in events}, registry)
        for fact in registry.all():
            family = family_of(fact.name)
            if family in by_family:
                continue
            row: dict[str, Any] = json.loads(
                fact.model_dump_json(by_alias=True, exclude_none=True)
            )
            row["label"] = desk_label_for(fact, ctx)
            by_family[family] = row
    return [by_family[k] for k in sorted(by_family)]


def main() -> int:
    rows = build()
    DEFAULT_OUT.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_OUT.write_text(
        json.dumps(rows, separators=(",", ":"), ensure_ascii=False) + "\n"
    )
    print(
        f"{len(rows)} families: {DEFAULT_OUT.relative_to(ROOT)}, {DEFAULT_OUT.stat().st_size} bytes"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
