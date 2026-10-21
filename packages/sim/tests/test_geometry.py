from contracts.models import PositionFrame
from sim.geometry import (
    back_line_height,
    hull_area,
    outfield_points,
    team_length,
    team_width,
)


def frame(
    home: list[tuple[float, float]], away: list[tuple[float, float]]
) -> PositionFrame:
    players = [
        {"id": f"{side}-{i + 1:02d}", "side": side, "at": [x, y], "role": "hold_slot"}
        for side, pts in (("home", home), ("away", away))
        for i, (x, y) in enumerate(pts)
    ]
    return PositionFrame.model_validate(
        {
            "match_id": "m-test",
            "t": 1.0,
            "ball": [60.0, 40.0],
            "possession": "home",
            "players": players,
        }
    )


SQUARE = [(30.0, 20.0), (50.0, 20.0), (50.0, 40.0), (30.0, 40.0), (40.0, 30.0)]


def test_hull_area_of_a_20_by_20_square() -> None:
    assert hull_area(SQUARE) == 400.0
    assert hull_area(SQUARE[:2]) == 0.0


def test_back_line_height_is_mirrored_for_away() -> None:
    assert back_line_height([(30.0, 10.0), (55.0, 40.0)], "home") == 30.0
    assert back_line_height([(90.0, 10.0), (65.0, 40.0)], "away") == 30.0


def test_length_and_width_on_a_hand_built_frame() -> None:
    pts = [(25.0, 12.0), (40.0, 68.0), (52.0, 30.0)]
    assert team_length(pts) == 27.0
    assert team_width(pts) == 56.0


def test_outfield_points_skip_the_goalkeeper_and_the_other_side() -> None:
    home = [(5.0, 40.0), (30.0, 20.0), (50.0, 60.0)] + [(60.0, 40.0)] * 8
    away = [(115.0, 40.0), (90.0, 20.0)] + [(70.0, 40.0)] * 9
    f = frame(home, away)
    assert outfield_points(f, "home")[:2] == [(30.0, 20.0), (50.0, 60.0)]
    assert len(outfield_points(f, "home")) == 10
    assert outfield_points(f, "away")[0] == (90.0, 20.0)
    assert (115.0, 40.0) not in outfield_points(f, "away")
