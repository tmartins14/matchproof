import pytest
from agents.narrator import (
    DraftClaim,
    Revision,
    build_prompt,
    load_examples,
    narrate,
    pick_examples,
)
from pydantic import ValidationError

BUNDLE = {
    "beat": {"kind": "momentum_swing", "label": "55–70′"},
    "facts": [
        {
            "id": "fx-1",
            "name": "back_line_drop",
            "label": "Ashford back line dropped deeper since the red card (63′)",
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
        assert all(
            e["beat_kind"] == kind or e["mode"] == mode for e in plain[:1]
        ) or not [e for e in examples if e["mode"] == mode or e["beat_kind"] == kind]


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
    assert (
        "fx-1" in prompt
        and "write as: 8 m / 8 metres" in prompt
        and "Ashford" in prompt
    )
    assert "back_line_drop" not in prompt  # the machine name never reaches the Narrator
    assert "Ashford look tired." in prompt and "No fact says tired." in prompt
    assert "AMENDED" in prompt and "{{" not in prompt


def test_claims_over_30_words_are_rejected() -> None:
    with pytest.raises(ValidationError):
        DraftClaim(text=" ".join(["word"] * 31), fact_ids=["fx-1"])


def test_the_prompt_for_a_real_bundle_has_no_machine_names_or_ids() -> None:
    import asyncio
    import re

    from agents.pipeline import tool_result
    from helpers import fill
    from mcp_match import InMemoryMatchStore, build_server

    store = InMemoryMatchStore()
    match_id = fill(store, "red_card_flip", 3)
    server = build_server(store, writable=False)
    teams = {"home": "Rivermouth", "away": "Ashford Vale"}
    for beat in store.beats(match_id):
        bundle = tool_result(
            asyncio.run(
                server.call_tool(
                    "get_beat_bundle", {"match_id": match_id, "beat_id": beat.id.root}
                )
            )
        )
        for mode in ("fan", "analyst"):
            prompt = build_prompt(bundle, mode, teams)  # type: ignore[arg-type]
            # Fact ids are cited by id and contain event ids; the JSON line names `fact_ids`.
            text = re.sub(
                r"fx-[A-Za-z0-9_.\-]+|fact_ids", "", prompt.split("Reply with JSON")[0]
            )
            found = re.findall(
                r"ev-\d{6}|\b(?:home|away)-\d{2}\b|\bt\d{3,}\.\d|[a-z]+_[a-z_]+", text
            )
            assert not found, (beat.id.root, mode, found)


def test_a_fan_beat_gets_at_most_two_claims() -> None:
    from fakes import FakeChat

    chat = FakeChat(
        [{"claims": [{"text": f"Claim {i}.", "fact_ids": ["fx-1"]} for i in range(3)]}]
    )
    out = narrate(chat, BUNDLE, "fan", teams=TEAMS)
    assert len(out.value.claims) == 2
