import pytest
from sim.brief import (
    DEFAULT_AWAY,
    DEFAULT_HOME,
    STORYLINES,
    custom_text,
    final_score,
    make_brief,
    validate_planted,
)

Spec = tuple[str, str, int, int]


def test_valid_custom_set_passes() -> None:
    beats: list[Spec] = [
        ("red_card", "away", 30, 35),
        ("open_play_goal", "home", 70, 80),
    ]
    assert validate_planted(beats) == []


@pytest.mark.parametrize("story", sorted(STORYLINES))
def test_presets_are_valid(story: str) -> None:
    assert validate_planted(STORYLINES[story].beats) == []


@pytest.mark.parametrize(
    ("beats", "message"),
    [
        ([("red_card", "home", 1, 3)] * 7, "at most 6 moments, not 7"),
        ([("counter_goal", "home", -1, 5)], "inside 0–95"),
        ([("counter_goal", "home", 90, 96)], "inside 0–95"),
        ([("counter_goal", "home", 30, 30)], "start before it ends"),
        ([("counter_goal", "home", 40, 50)], "spans half-time"),
        ([("penalty", "home", 30, 31)], "at least 2 minutes"),
        (
            [("red_card", "away", 10, 15), ("red_card", "away", 60, 65)],
            "at most one red card per side; away has 2",
        ),
        (
            [("counter_goal", "home", 10, 20), ("set_piece_goal", "home", 21, 30)],
            "at least 2 minutes apart",
        ),
        (
            [("open_play_goal", "away", 60, 70), ("penalty", "away", 65, 75)],
            "Two away goals",
        ),
        (
            [("red_card", "home", 20, 30), ("counter_goal", "away", 25, 35)],
            "overlapping windows",
        ),
    ],
)
def test_each_rule_fails_with_a_message(beats: list[Spec], message: str) -> None:
    errors = validate_planted(beats)
    assert errors and any(message in e for e in errors), errors


def test_red_cards_on_both_sides_and_goals_on_both_sides_are_fine() -> None:
    beats: list[Spec] = [
        ("red_card", "home", 20, 25),
        ("red_card", "away", 25, 30),
        ("counter_goal", "home", 30, 40),
        ("counter_goal", "away", 40, 45),
    ]
    assert validate_planted(beats) == []


def test_score_counts_penalties_and_not_cards() -> None:
    beats: list[Spec] = [
        ("penalty", "home", 10, 20),
        ("counter_goal", "away", 30, 40),
        ("red_card", "away", 50, 55),
    ]
    assert final_score(beats) == (1, 1)


def test_custom_text_and_brief() -> None:
    beats: list[Spec] = [("red_card", "away", 30, 35), ("counter_goal", "home", 70, 80)]
    assert (
        custom_text(DEFAULT_HOME, DEFAULT_AWAY, beats)
        == "Custom: Ashford Vale red card 30–35′; Rivermouth goal 70–80′"
    )
    brief = make_brief(storyline_id="custom", seed=3, planted=beats)
    assert brief.storyline.text.startswith("Custom: ")
    assert brief.brief_text is not None and brief.storyline.text in brief.brief_text
    assert [pb.id for pb in brief.planted_beats] == ["pb-01", "pb-02"]
