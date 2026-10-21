"""Hand-built events and frames for known-answer tests."""

from typing import Any

from contracts.models import Event, PositionFrame

Pt = tuple[float, float]


def event(
    n: int,
    kind: str,
    side: str,
    t: float,
    at: Pt,
    *,
    period: int = 1,
    outcome: str | None = None,
    player: str | None = None,
    possession: int | None = None,
    end: Pt | None = None,
    xg: float | None = None,
) -> Event:
    raw: dict[str, Any] = {
        "id": f"ev-{n:06d}",
        "match_id": "m-test",
        "seq": n - 1,
        "period": period,
        "t": t,
        "side": side,
        "type": kind,
        "location": list(at),
    }
    if outcome:
        raw["outcome"] = outcome
    if player:
        raw["player_id"] = player
    if possession is not None:
        raw["possession_id"] = possession
    if end:
        raw["end_location"] = list(end)
    if xg is not None:
        raw["shot"] = {"xg": xg, "body_part": "right_foot"}
    return Event.model_validate(raw)


def frame(
    home: list[Pt],
    away: list[Pt],
    ball: Pt = (60.0, 40.0),
    t: float = 0.0,
    possession: str = "home",
    freeze_of: str | None = None,
) -> PositionFrame:
    """A frame from 10 outfield positions per side; each side's keeper stands on its goal line."""
    assert len(home) == 10 and len(away) == 10
    players = [{"id": "home-01", "side": "home", "at": [1.0, 40.0]}] + [
        {"id": f"home-{i + 2:02d}", "side": "home", "at": list(p)}
        for i, p in enumerate(home)
    ]
    players += [{"id": "away-01", "side": "away", "at": [119.0, 40.0]}] + [
        {"id": f"away-{i + 2:02d}", "side": "away", "at": list(p)}
        for i, p in enumerate(away)
    ]
    raw: dict[str, Any] = {
        "match_id": "m-test",
        "t": t,
        "ball": list(ball),
        "possession": possession,
        "players": players,
    }
    if freeze_of:
        raw["freeze_frame_of"] = freeze_of
    return PositionFrame.model_validate(raw)


def spread(x_deepest: float, y: float = 40.0) -> list[Pt]:
    """Ten outfielders in a loose column starting at x_deepest, for frames where only some of them matter."""
    return [(x_deepest + 3.0 * i, y + (i % 5 - 2) * 8.0) for i in range(10)]
