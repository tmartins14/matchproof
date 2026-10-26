"""Draw the freeze frame of one pass as SVG, with the old and the new positions side by side.

    uv run python -m scripts.realism_freeze --old-positions <file> --fixture fx-01 --out docs/realism

The old positions come from a copy of positions.py (git show <rev>:packages/sim/src/sim/positions.py).
The pass is the first forward pass in the fixture that the old positions leave offside by 4 m or more.
"""

import argparse
import sys
import types
from collections.abc import Callable, Iterator
from pathlib import Path

from contracts.models import Event, MatchBrief, PositionFrame
from sim import iter_events
from sim.realism import Pos, forward_pass, is_offside, positions

from evals.trials import load_pack

Runner = Callable[
    [MatchBrief, Iterator[Event]],
    Iterator[tuple[str, Event | None, PositionFrame | None]],
]


def load_old(path: Path) -> Runner:
    mod = types.ModuleType("sim.positions_old")
    mod.__package__ = "sim"
    sys.modules[mod.__name__] = mod
    exec(compile(path.read_text("utf-8"), str(path), "exec"), mod.__dict__)  # noqa: S102
    runner: Runner = mod.run
    return runner


def freezes(run: Runner, brief: MatchBrief) -> Iterator[tuple[Event, PositionFrame]]:
    last: Event | None = None
    for kind, event, frame in run(brief, iter_events(brief)):
        if kind == "event":
            last = event
        elif kind == "freeze" and last is not None and frame is not None:
            yield last, frame


def margin(e: Event, players: list[Pos]) -> float:
    """Metres the receiver stands beyond the offside line (negative: onside)."""
    assert e.pass_ is not None and e.pass_.recipient_id is not None
    sign = 1.0 if e.side.value == "home" else -1.0
    others = sorted(
        (sign * p.x for p in players if p.side != e.side.value), reverse=True
    )
    me = next(p for p in players if p.id == e.pass_.recipient_id.root)
    line = max(others[1], sign * e.location.root[0].root)
    return sign * me.x - line


def svg(e: Event, frame: PositionFrame, title: str) -> str:
    players = positions(frame)
    assert e.pass_ is not None and e.pass_.recipient_id is not None
    sign = 1.0 if e.side.value == "home" else -1.0
    others = sorted(
        (sign * p.x for p in players if p.side != e.side.value), reverse=True
    )
    line_x = sign * others[1]
    verdict = is_offside(
        e.side.value, e.pass_.recipient_id.root, e.location.root[0].root, players
    )
    s = 8
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-10 -30 {120 * s + 20} {80 * s + 70}" width="{120 * s // 2}">',
        '<rect x="-10" y="-30" width="100%" height="100%" fill="#fff"/>',
        f'<rect x="0" y="0" width="{120 * s}" height="{80 * s}" fill="#e8f1e4" stroke="#6b8f63"/>',
        f'<line x1="{60 * s}" y1="0" x2="{60 * s}" y2="{80 * s}" stroke="#6b8f63"/>',
        f'<line x1="{line_x * s}" y1="0" x2="{line_x * s}" y2="{80 * s}" stroke="#c0392b" stroke-dasharray="6 4"/>',
    ]
    for p in players:
        mine = p.side == e.side.value
        colour = "#1f5fa8" if mine else "#b8501f"
        recv = p.id == e.pass_.recipient_id.root
        out.append(
            f'<circle cx="{p.x * s:.0f}" cy="{p.y * s:.0f}" r="{9 if recv else 6}" fill="{colour}"'
            + (' stroke="#000" stroke-width="3"' if recv else "")
            + "/>"
        )
    bx, by = e.location.root[0].root, e.location.root[1].root
    ex, ey = (
        e.end_location.root[0].root if e.end_location else bx,
        e.end_location.root[1].root if e.end_location else by,
    )
    out.append(
        f'<line x1="{bx * s}" y1="{by * s}" x2="{ex * s}" y2="{ey * s}" stroke="#222" stroke-dasharray="3 3"/>'
    )
    out.append(
        f'<circle cx="{bx * s}" cy="{by * s}" r="4" fill="#fff" stroke="#000" stroke-width="2"/>'
    )
    word = "OFFSIDE" if verdict else "onside"
    out.append(
        f'<text x="0" y="-12" font-family="sans-serif" font-size="18">{title}: {e.id.root} at {e.t.root:.0f} s. '
        f"Receiver {e.pass_.recipient_id.root} (ringed) is {word}.</text>"
    )
    out.append(
        '<text x="0" y="662" font-family="sans-serif" font-size="14" fill="#555">'
        "Blue attacks right. Red dashed line: second-last defender. White dot: the ball at the pass.</text>"
    )
    out.append("</svg>")
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--old-positions", type=Path, required=True)
    ap.add_argument("--fixture", default="fx-01")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    from sim.positions import run as new_run

    brief = next(f for f in load_pack()[1] if f.id == a.fixture).make_brief()
    old_run = load_old(a.old_positions)
    chosen: str | None = None
    old_frame: PositionFrame | None = None
    event: Event | None = None
    for e, fr in freezes(old_run, brief):
        if (
            forward_pass(e)
            and e.pass_ is not None
            and e.side.value == "home"
            and 20 < e.t.root < 2400
            and margin(e, positions(fr)) >= 4.0
        ):
            chosen, old_frame, event = e.id.root, fr, e
            break
    assert chosen and old_frame and event, "no offside pass found"
    new_frame = next(fr for e, fr in freezes(new_run, brief) if e.id.root == chosen)
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "freeze-before.svg").write_text(
        svg(event, old_frame, "before"), encoding="utf-8"
    )
    (a.out / "freeze-after.svg").write_text(
        svg(event, new_frame, "after"), encoding="utf-8"
    )
    print(
        chosen,
        round(margin(event, positions(old_frame)), 1),
        round(margin(event, positions(new_frame)), 1),
    )


if __name__ == "__main__":
    main()
