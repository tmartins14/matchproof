import re

import pytest
from contracts.models import Event
from intel.display import minute_text, render_minute
from intel.labels import LabelContext, label_for, say
from matches import lean

TEAMS = {"home": "Rivermouth", "away": "Ashford Vale"}


@pytest.fixture(scope="module")
def red_card() -> tuple[LabelContext, dict[str, str]]:
    m = lean("red_card_flip", 3)
    events: dict[str, Event] = {e.id.root: e for e in m.events}
    ctx = LabelContext(TEAMS, events, m.registry)
    labels = {f.name: label_for(f, ctx) for f in m.registry.all()}
    return ctx, labels


def test_known_labels(red_card: tuple[LabelContext, dict[str, str]]) -> None:
    _, labels = red_card
    assert labels["back_line_height(away, before ev-001484)"] == (
        "Ashford Vale back line, before the red card (63′)"
    )
    assert labels["back_line_height(away, since ev-001484 to t4671.00)"] == (
        "Ashford Vale back line, since the red card (63′)"
    )
    assert labels["shot(ev-000222).xg"] == "chance quality (xG)"
    assert labels["card(ev-001484).kind"].endswith(", second yellow, sent off")
    assert labels["card(ev-001479).kind"].endswith(", yellow card")


def test_since_spans_name_the_anchor_event_and_never_its_id(
    red_card: tuple[LabelContext, dict[str, str]],
) -> None:
    _, labels = red_card
    since = {
        n: label for n, label in labels.items() if "ev-001484" in n and "since" in n
    }
    assert since
    for name, label in since.items():
        assert "the red card (63′)" in label, name
        assert "ev-" not in label


def test_goal_anchor_names_the_scoring_team(
    red_card: tuple[LabelContext, dict[str, str]],
) -> None:
    _, labels = red_card
    goal = next(
        n for n in labels if n.startswith("possession_share(home, since ev-001670")
    )
    assert "since Rivermouth's goal (71′)" in labels[goal]


def test_change_label_reads_the_direction_from_the_before_and_since_facts(
    red_card: tuple[LabelContext, dict[str, str]],
) -> None:
    _, labels = red_card
    change = labels["back_line_change(away, ev-001484, to t4671.00)"]
    assert (
        change
        == "Ashford Vale back line dropped deeper since the red card (63′) (size of the change)"
    )


def test_no_label_leaks_a_machine_token(
    red_card: tuple[LabelContext, dict[str, str]],
) -> None:
    _, labels = red_card
    assert len(labels) > 500
    for name, label in labels.items():
        assert not re.search(r"ev-\d|_|\bt\d{3,}\.|\bwin-", label), (name, label)


def test_clock_facts_use_the_broadcast_minute() -> None:
    # 5,842 s of period 2 is 97:22, the 98th minute: 90+8, as the beat labels call it.
    assert minute_text(5842, 2) == "90+8"
    assert render_minute(5842, "en", 2) == ["90+8′"]
    assert minute_text(46 * 60 + 5, 1) == "45+2"
    assert render_minute(40.2 * 60, "en") == ["41′"]


def test_sequence_clock_facts_render_as_minutes_not_mm_ss() -> None:
    m = lean("red_card_flip", 3)
    clocks = [
        f for f in m.registry.all() if f.name.endswith((".start_clock", ".shot_clock"))
    ]
    assert clocks
    for f in clocks:
        assert re.fullmatch(r"\d+(\+\d+)?′", f.display.en[0]), f.display.en


def test_say_turns_machine_values_into_words() -> None:
    assert say("away-10", ["away-10"], TEAMS) == ["the Ashford Vale No. 10"]
    assert say("second_yellow", ["second_yellow"], TEAMS) == ["second yellow"]
    assert say("Pryce", ["Pryce"], TEAMS) == ["Pryce"]
    assert say(0.3, ["0.30 xG", "0.3 xG"], TEAMS) == ["0.30 xG", "0.3 xG"]
