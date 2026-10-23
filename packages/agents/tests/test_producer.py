from typing import Any

from agents.llm_client import LlmError
from agents.producer import NARRATION_BUDGET, SAME_KIND_GAP_S, Producer
from fakes import FakeChat

TEAMS = {"home": "Ashford Vale", "away": "Rivermouth"}


def beat(i: int, kind: str, t: float, salience: float = 0.5) -> dict[str, Any]:
    return {
        "id": f"bt-{i:06d}-{kind}",
        "kind": kind,
        "t_from": t,
        "label": f"{int(t // 60)}′",
        "salience": salience,
        "side": "home",
    }


def says(narrate: bool, priority: int = 3) -> dict[str, Any]:
    return {"narrate": narrate, "priority": priority, "note": "A chance worth showing."}


def test_goals_red_cards_and_follow_ups_are_narrated_even_if_the_model_says_no() -> (
    None
):
    client = FakeChat([says(False)] * 20)
    producer = Producer(client)
    kinds = ["open_play_goal", "card", "momentum_swing", "counter_goal"]
    out = [producer.decide(beat(i, k, 100.0 * i), TEAMS) for i, k in enumerate(kinds)]
    assert all(d.narrate and d.forced for d in out)
    assert client.prompts == []  # nobody was asked


def test_the_budget_caps_judged_narrations() -> None:
    producer = Producer(FakeChat([says(True)] * 40))
    out = [producer.decide(beat(i, "big_chance", 600.0 * i), TEAMS) for i in range(20)]
    assert sum(d.narrate for d in out) == NARRATION_BUDGET
    assert all(d.reason == "budget" for d in out[NARRATION_BUDGET:])


def test_goals_are_not_held_back_by_a_full_budget() -> None:
    producer = Producer(FakeChat([says(True)] * 40))
    for i in range(NARRATION_BUDGET + 3):
        producer.decide(beat(i, "big_chance", 600.0 * i), TEAMS)
    assert producer.decide(beat(99, "open_play_goal", 9000.0), TEAMS).narrate


def test_two_beats_of_one_kind_are_not_narrated_within_three_minutes() -> None:
    producer = Producer(FakeChat([says(True)] * 5))
    first = producer.decide(beat(1, "big_chance", 1000.0), TEAMS)
    near = producer.decide(beat(2, "big_chance", 1000.0 + SAME_KIND_GAP_S - 1), TEAMS)
    other = producer.decide(beat(3, "high_turnover_chance", 1010.0), TEAMS)
    later = producer.decide(beat(4, "big_chance", 1000.0 + SAME_KIND_GAP_S), TEAMS)
    assert (first.narrate, near.narrate, other.narrate, later.narrate) == (
        True,
        False,
        True,
        True,
    )
    assert near.reason == "spacing"


def test_goals_may_come_close_together() -> None:
    producer = Producer(None)
    a = producer.decide(beat(1, "open_play_goal", 1000.0), TEAMS)
    b = producer.decide(beat(2, "open_play_goal", 1060.0), TEAMS)
    assert a.narrate and b.narrate


def test_ranks_run_from_one_with_no_gaps() -> None:
    answers = [says(True), says(False), says(True), says(True), says(False)]
    producer = Producer(FakeChat(answers))
    kinds = [
        "big_chance",
        "territorial_spell",
        "high_turnover_chance",
        "card",
        "big_chance",
    ]
    out = [producer.decide(beat(i, k, 700.0 * i), TEAMS) for i, k in enumerate(kinds)]
    ranks = [d.rank for d in out if d.narrate]
    assert ranks == list(range(1, len(ranks) + 1))
    assert all(d.rank is None for d in out if not d.narrate)


def test_the_model_is_told_what_has_been_narrated() -> None:
    client = FakeChat([says(True), says(True)])
    producer = Producer(client)
    producer.decide(beat(1, "big_chance", 600.0), TEAMS)
    producer.decide(beat(2, "territorial_spell", 2000.0), TEAMS)
    assert "big chance at 10′" in client.prompts[1]
    assert "nothing yet" in client.prompts[0]


def test_a_failing_model_falls_back_to_salience_and_the_log_says_so() -> None:
    producer = Producer(FakeChat([LlmError("APITimeoutError")] * 2))
    high = producer.decide(beat(1, "big_chance", 600.0, 0.9), TEAMS)
    low = producer.decide(beat(2, "territorial_spell", 2000.0, 0.2), TEAMS)
    assert (high.narrate, low.narrate) == (True, False)
    assert high.reason == low.reason == "fallback"


def test_a_note_that_breaks_a_voice_rule_is_replaced() -> None:
    bad = {"narrate": True, "priority": 3, "note": "A brilliant big_chance — see it."}
    producer = Producer(FakeChat([bad]))
    d = producer.decide(beat(1, "big_chance", 600.0), TEAMS)
    assert "brilliant" not in d.note and "—" not in d.note and "_" not in d.note
