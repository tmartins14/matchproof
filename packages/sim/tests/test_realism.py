from contracts.models import Event, PositionFrame
from sim.realism import (
    MAX_ACCEL_MS2,
    MAX_SPEED_MS,
    Motion,
    Pos,
    Report,
    back_line_spread,
    forward_pass,
    is_offside,
    offside_at_pass,
    overlapping,
)


def line_up(x_last: float, x_second: float) -> list[Pos]:
    """Away defenders at the given x (second-last and last standing as asked) plus a home runner at 100."""
    return [
        Pos("away-01", "away", 118.0, 40.0),
        Pos("away-02", "away", x_last, 30.0),
        Pos("away-03", "away", x_second, 50.0),
        Pos("home-09", "home", 100.0, 40.0),
    ]


def test_beyond_ball_and_second_last_is_offside() -> None:
    # Away: goalkeeper 118, then 95 and 90. Second-last (from the goal) is the 95 defender.
    assert is_offside("home", "home-09", 80.0, line_up(95.0, 90.0)) is True


def test_level_with_second_last_is_onside() -> None:
    players = line_up(100.0, 90.0)
    assert is_offside("home", "home-09", 80.0, players) is False


def test_behind_the_ball_is_onside() -> None:
    assert is_offside("home", "home-09", 105.0, line_up(95.0, 90.0)) is False


def test_own_half_is_onside() -> None:
    players = [
        Pos("away-01", "away", 118.0, 40.0),
        Pos("away-02", "away", 30.0, 30.0),
        Pos("home-09", "home", 50.0, 40.0),
    ]
    assert is_offside("home", "home-09", 40.0, players) is False


def test_away_side_attacks_toward_zero() -> None:
    players = [
        Pos("home-01", "home", 2.0, 40.0),
        Pos("home-02", "home", 25.0, 30.0),
        Pos("away-09", "away", 20.0, 40.0),
    ]
    assert is_offside("away", "away-09", 60.0, players) is True


def test_unknown_receiver_is_none() -> None:
    assert is_offside("home", "home-99", 80.0, line_up(95.0, 90.0)) is None


def test_overlap_and_back_line() -> None:
    assert overlapping([Pos("home-02", "home", 10, 10), Pos("home-03", "home", 11, 10)])
    assert not overlapping(
        [Pos("home-02", "home", 10, 10), Pos("away-03", "away", 10.5, 10)]
    )
    players = [Pos(f"home-{i:02d}", "home", float(i), 10.0) for i in range(1, 11)]
    assert (
        back_line_spread("home", players) == 3.0
    )  # slots 2 to 5, the goalkeeper left out


def test_motion_flags_speed_and_skips_pinned_steps() -> None:
    m = Motion()
    for k in range(10):
        m.push(k * 0.2, [Pos("home-02", "home", 1.7 * k, 10.0)])  # 8.5 m/s, steady
    assert 8.0 < m.max_speed["home-02"] < MAX_SPEED_MS
    assert m.max_accel["home-02"] < 1.0
    m.push(2.0, [Pos("home-02", "home", 60.0, 10.0)], frozenset({"home-02"}))  # placed
    assert m.snap_jumps == 1 and m.max_speed["home-02"] < MAX_SPEED_MS


def test_motion_measures_acceleration() -> None:
    m = Motion()
    x = v = 0.0
    for k in range(20):
        m.push(k * 0.2, [Pos("home-02", "home", x, 10.0)])
        v += 4.0 * 0.2
        x += v * 0.2
    assert 3.5 < m.max_accel["home-02"] < MAX_ACCEL_MS2


def test_forward_pass_needs_recipient_and_direction() -> None:
    def pass_event(start: float, end: float, side: str) -> Event:
        return Event.model_validate(
            {
                "id": "ev-000001",
                "match_id": "m",
                "seq": 1,
                "period": 1,
                "t": 1.0,
                "side": side,
                "player_id": f"{side}-02",
                "type": "pass",
                "location": [start, 40.0],
                "end_location": [end, 40.0],
                "pass": {"recipient_id": f"{side}-09"},
            }
        )

    assert forward_pass(pass_event(50.0, 70.0, "home"))
    assert not forward_pass(pass_event(70.0, 50.0, "home"))
    assert forward_pass(pass_event(70.0, 50.0, "away"))


def test_offside_at_pass_reads_the_freeze_frame() -> None:
    event = Event.model_validate(
        {
            "id": "ev-000007",
            "match_id": "m",
            "seq": 7,
            "period": 1,
            "t": 5.0,
            "side": "home",
            "player_id": "home-02",
            "type": "pass",
            "location": [80.0, 40.0],
            "end_location": [105.0, 40.0],
            "pass": {"recipient_id": "home-09"},
        }
    )

    def frame(runner_x: float) -> PositionFrame:
        players = [
            ("away-01", "away", 118.0),
            ("away-02", "away", 95.0),
            ("away-03", "away", 90.0),
            ("home-09", "home", runner_x),
        ]
        players += [(f"away-{n:02d}", "away", 70.0) for n in range(4, 12)]
        players += [(f"home-{n:02d}", "home", 30.0) for n in range(1, 12) if n != 9]
        return PositionFrame.model_validate(
            {
                "match_id": "m",
                "t": 5.0,
                "ball": [80.0, 40.0],
                "possession": "home",
                "freeze_frame_of": "ev-000007",
                "players": [
                    {
                        "id": i,
                        "side": s,
                        "at": [x, 40.0],
                        "speed_ms": 0.0,
                        "role": "hold_slot",
                    }
                    for i, s, x in players
                ],
            }
        )

    assert offside_at_pass([frame(100.0)], [event]) == (1, 1)
    assert offside_at_pass([frame(94.0)], [event]) == (0, 1)
    assert Report().summary()["offside_share"] == 0.0
