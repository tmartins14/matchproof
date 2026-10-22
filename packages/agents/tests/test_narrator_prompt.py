import pytest
from agents.narrator import (
    DraftClaim,
    Revision,
    build_prompt,
    load_examples,
    pick_examples,
)
from pydantic import ValidationError

BUNDLE = {
    "beat": {"kind": "momentum_swing", "label": "55–70′"},
    "facts": [
        {
            "id": "fx-1",
            "name": "back_line_drop",
            "value": 8,
            "display": {"en": ["8 m", "8 metres"]},
            "scope": {"side": "home"},
        }
    ],
}
TEAMS = {"home": "Ashford", "away": "Rivermouth"}


def test_examples_match_kind_and_mode_and_include_an_amended_pair() -> None:
    examples = load_examples()
    for kind, mode in [
        ("momentum_swing", "analyst"),
        ("card", "fan"),
        ("counter_goal", "producer"),
    ]:
        picked = pick_examples(examples, kind, mode)
        assert 4 <= len(picked) <= 6
        assert sum(1 for e in picked if e.get("amended_from")) == 1
        plain = [e for e in picked if not e.get("amended_from")]
        assert all(e["beat_kind"] == kind or e["mode"] == mode for e in plain[:2])


def test_matching_examples_come_first() -> None:
    picked = pick_examples(load_examples(), "momentum_swing", "analyst")
    assert picked[0]["beat_kind"] == "momentum_swing" and picked[0]["mode"] == "analyst"


def test_format_only_example_is_never_used() -> None:
    assert all(e["id"] != "ex-00" for e in load_examples())
    for kind in ("counter_goal", "card", "big_chance"):
        for mode in ("fan", "analyst", "producer"):
            assert all(
                e["id"] != "ex-00" for e in pick_examples(load_examples(), kind, mode)
            )
    assert "ex-00" not in build_prompt(BUNDLE, "fan", TEAMS)


def test_prompt_has_facts_teams_and_the_revision() -> None:
    prompt = build_prompt(
        BUNDLE,
        "fan",
        TEAMS,
        Revision(
            [DraftClaim(text="Ashford look tired.", fact_ids=["fx-1"])],
            ["No fact says tired."],
        ),
    )
    assert "fx-1" in prompt and "8 m | 8 metres" in prompt and "Ashford" in prompt
    assert "Ashford look tired." in prompt and "No fact says tired." in prompt
    assert "AMENDED" in prompt and "{{" not in prompt


def test_claims_over_30_words_are_rejected() -> None:
    with pytest.raises(ValidationError):
        DraftClaim(text=" ".join(["word"] * 31), fact_ids=["fx-1"])
