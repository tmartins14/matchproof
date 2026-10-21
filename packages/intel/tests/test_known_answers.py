from builders import event, frame
from intel.extract_events import EventObserver, Span, span_facts
from intel.extract_positions import (
    freeze_facts,
    make_sample,
    position_facts,
)

SPAN = Span("win-01", 1, 0.0, 900.0, ("win-01",))


def values(facts: list, side: str) -> dict[str, float]:  # type: ignore[type-arg]
    return {
        f.name.split("(")[0]: f.value
        for f in facts
        if f.scope is not None
        and f.scope.side is not None
        and f.scope.side.value == side
    }


def four_event_sequence() -> list:  # type: ignore[type-arg]
    """Home wins the ball 31 m from goal, passes twice (one lost), then shoots; one away pass."""
    return [
        event(
            1,
            "tackle",
            "home",
            100.0,
            (90.0, 40.0),
            outcome="won",
            player="home-08",
            possession=7,
        ),
        event(
            2,
            "pass",
            "home",
            103.0,
            (90.0, 40.0),
            outcome="complete",
            end=(100.0, 40.0),
            possession=7,
        ),
        event(
            3,
            "pass",
            "home",
            106.0,
            (100.0, 40.0),
            outcome="incomplete",
            end=(105.0, 45.0),
            possession=7,
        ),
        event(
            4,
            "shot",
            "home",
            111.0,
            (104.0, 40.0),
            outcome="saved",
            possession=7,
            xg=0.41,
        ),
        event(
            5,
            "pass",
            "away",
            120.0,
            (50.0, 40.0),
            outcome="complete",
            end=(40.0, 40.0),
            possession=8,
        ),
    ]


def test_counts_and_shares_on_a_hand_built_sequence() -> None:
    v = values(span_facts(four_event_sequence(), SPAN), "home")
    assert v["passes"] == 2 and v["shots"] == 1 and v["goals"] == 0
    assert v["pass_completion"] == 0.5
    assert v["xg"] == 0.41
    assert v["possession_share"] == 0.5  # one completed pass each
    assert v["high_turnovers"] == 1  # won 30 m from goal
    assert (
        values(span_facts(four_event_sequence(), SPAN), "away")["possession_share"]
        == 0.5
    )


def test_sequence_facts_for_a_possession_ending_in_a_shot() -> None:
    obs = EventObserver()
    facts = [f for e in four_event_sequence() for f in obs.observe(e)]
    by_name = {f.name: f for f in facts}
    assert by_name["sequence(ev-000004).seconds"].value == 11.0
    assert by_name["sequence(ev-000004).passes"].value == 2
    assert round(float(by_name["sequence(ev-000004).ball_won_distance"].value)) == 30
    assert by_name["sequence(ev-000004).start_clock"].display.en == ["1:40"]
    assert [s.root for s in by_name["sequence(ev-000004).seconds"].source_ids] == [
        "ev-000001",
        "ev-000002",
        "ev-000003",
        "ev-000004",
    ]
    assert by_name["shot(ev-000004).xg"].display.en == ["0.41 xG", "0.4 xG"]
    assert by_name["shot(ev-000004).on_target"].value is True


def square(x0: float, y0: float, size: float) -> list[tuple[float, float]]:
    """Ten points on or inside a square, corners included."""
    c = [(x0, y0), (x0 + size, y0), (x0 + size, y0 + size), (x0, y0 + size)]
    return c + [(x0 + size / 2, y0 + size / 2 + i) for i in range(6)]


def test_twenty_by_twenty_square_is_four_hundred_square_metres() -> None:
    f = frame(square(50.0, 30.0, 20.0), square(70.0, 30.0, 20.0), t=3.0)
    sample = make_sample(f)
    assert sample is not None and sample.home is not None
    assert sample.home.area == 400.0
    assert sample.home.length == 20.0 and sample.home.width == 20.0


def test_back_line_is_thirty_metres_for_both_sides() -> None:
    home = [(30.0, 10.0 + 6 * i) for i in range(1)] + [
        (40.0 + i, 20.0 + 3 * i) for i in range(9)
    ]
    away = [(90.0, 10.0)] + [(80.0 - i, 20.0 + 3 * i) for i in range(9)]
    samples = [
        make_sample(frame(home, away, t=float(t), possession="away")) for t in range(6)
    ]
    window = Span("win-01", 1, 0.0, 900.0, ("win-01",))
    facts = position_facts([s for s in samples if s is not None], window)
    by_name = {f.name: f.value for f in facts}
    assert by_name["back_line_height(home, win-01, out_of_possession)"] == 30.0
    assert by_name["back_line_height(away, win-01, in_possession)"] == 30.0


def test_off_grid_frames_are_not_sampled() -> None:
    f = frame(square(50.0, 30.0, 20.0), square(70.0, 30.0, 20.0), t=3.2)
    assert make_sample(f) is None


def test_nearest_defender_at_a_shot_is_two_metres() -> None:
    shot = event(
        9, "shot", "home", 50.0, (100.0, 40.0), player="home-11", xg=0.3, outcome="wide"
    )
    home = [(100.0, 40.0)] + [(60.0, 10.0 + 6 * i) for i in range(9)]
    away = [(102.0, 40.0)] + [(110.0, 20.0 + 5 * i) for i in range(9)]
    ff = frame(home, away, ball=(100.0, 40.0), t=50.0, freeze_of="ev-000009")
    by_name = {f.name: f for f in freeze_facts(shot, ff)}
    nearest = by_name["freeze_frame(ev-000009).shooter_nearest_defender"]
    assert nearest.value == 2.0 and nearest.display.en == ["2 m", "2 metres"]
    assert [s.root for s in nearest.source_ids] == ["ev-000009", "ff-000009"]


def test_three_v_one_and_players_ahead_of_the_ball() -> None:
    kick = event(5, "tackle", "away", 70.0, (60.0, 40.0), outcome="won")
    # Away attack toward x = 0. Three away players ahead of the ball in its zone, one home defender.
    away = [(50.0, 35.0), (45.0, 40.0), (40.0, 45.0)] + [
        (80.0, 10.0 + 8 * i) for i in range(7)
    ]
    home = [(30.0, 40.0)] + [(75.0, 10.0 + 8 * i) for i in range(9)]
    ff = frame(
        home, away, ball=(60.0, 40.0), t=70.0, possession="away", freeze_of="ev-000005"
    )
    by_name = {f.name: f for f in freeze_facts(kick, ff)}
    assert by_name["freeze_frame(ev-000005).attackers_v_defenders"].value == "3 v 1"
    assert by_name["freeze_frame(ev-000005).attackers_ahead_of_ball"].value == 3
    # Home attack toward x = 120: the nine home players at x = 75 are ahead of a ball at x = 60.
    assert by_name["freeze_frame(ev-000005).home_ahead_of_ball"].value == 9
    assert by_name["freeze_frame(ev-000005).away_ahead_of_ball"].value == 3
