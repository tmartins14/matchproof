from typing import Any

import pytest
from agents.composer import ComposerAnswer, check, compose
from agents.llm_client import LlmError
from fakes import FakeChat
from sim.brief import validate_planted


def team(formation: str = "4-3-3", **dials: float) -> dict[str, Any]:
    return {
        "formation": formation,
        "press": 0.5,
        "directness": 0.5,
        "line_height": 0.5,
    } | dials


def reply(
    storyline: str = "custom", moments: list[dict[str, Any]] | None = None, **teams: Any
) -> dict[str, Any]:
    return {
        "home": teams.get("home", team()),
        "away": teams.get(
            "away", team("4-4-2", press=0.1, directness=0.9, line_height=0.2)
        ),
        "storyline": storyline,
        "moments": moments or [],
    }


def moment(kind: str, side: str, lo: int, hi: int) -> dict[str, Any]:
    return {"kind": kind, "side": side, "minute_from": lo, "minute_to": hi}


def planted(result: Any) -> list[tuple[str, str, int, int]]:
    return [
        (p.kind.value, p.side.value, p.minute_from, p.minute_to)
        for p in result.brief.planted_beats
    ]


def test_valid_output_passes_through() -> None:
    chat = FakeChat([reply(moments=[moment("red_card", "away", 38, 45)])])
    out = compose(chat, "Ashford sit deep and lose a man before half-time")
    assert out.warnings == []
    assert len(chat.prompts) == 1
    assert out.brief.away.formation.value == "4-4-2"
    assert out.brief.away.press.root == 0.1
    assert planted(out) == [("red_card", "away", 38, 45)]
    assert out.brief.storyline.id.value == "custom"
    assert "Custom: Ashford Vale red card 38–45′" in out.brief_text
    assert out.brief_text == out.brief.brief_text
    assert "Ashford Vale (4-4-2) drop off" in out.brief_text


def test_preset_storyline() -> None:
    out = compose(
        FakeChat([reply("smash_and_grab")]), "Rivermouth dominate and lose 1-0"
    )
    assert out.brief.storyline.id.value == "smash_and_grab"
    assert out.warnings == []


def test_invalid_output_retries_once_with_the_errors() -> None:
    bad = reply(
        moments=[moment("red_card", "away", 10, 15), moment("red_card", "away", 60, 65)]
    )
    good = reply(moments=[moment("red_card", "away", 10, 15)])
    chat = FakeChat([bad, good])
    out = compose(chat, "Ashford lose a man")
    assert len(chat.prompts) == 2
    assert "at most one red card per side" in chat.prompts[1]
    assert out.warnings == []
    assert planted(out) == [("red_card", "away", 10, 15)]


def test_second_failure_returns_a_valid_partial_with_warnings() -> None:
    bad = reply(
        moments=[moment("counter_goal", "home", 0, 5) for _ in range(7)],
        home=team("9-9-9", press=1.7),
    )
    chat = FakeChat([bad, bad])
    out = compose(chat, "Rivermouth score 7 in the first 5 minutes")
    assert len(chat.prompts) == 2
    assert planted(out) == [("counter_goal", "home", 0, 5)]
    assert (
        out.brief.home.formation.value == "4-3-3"
    )  # the default, since 9-9-9 is not real
    assert out.brief.home.press.root == 1.0
    assert any("formation" in w for w in out.warnings)
    assert any("press" in w for w in out.warnings)
    assert sum("Left out:" in w for w in out.warnings) == 6
    assert validate_planted(planted(out)) == []


def test_output_never_bypasses_validate_planted() -> None:
    wild = reply(
        moments=[
            moment("penalty", "home", 30, 31),
            moment("counter_goal", "away", -5, 3),
            moment("red_card", "home", 40, 50),
            moment("nonsense", "home", 10, 20),
            moment("red_card", "sideways", 10, 20),
            moment("red_card", "home", 50, 55),
            moment("red_card", "home", 60, 65),
        ]
    )
    out = compose(FakeChat([wild, wild]), "anything")
    assert planted(out) == [("red_card", "home", 50, 55)]
    assert validate_planted(planted(out)) == []
    assert len(out.warnings) == 6


def test_preset_with_moments_is_an_error_then_a_warning() -> None:
    mixed = reply("end_to_end", [moment("red_card", "home", 10, 15)])
    assert check(ComposerAnswer.model_validate(mixed))
    out = compose(FakeChat([mixed, mixed]), "x")
    assert planted(out) == [("red_card", "home", 10, 15)]
    assert any("preset" in w for w in out.warnings)


def test_unreadable_answers_fall_back_to_defaults() -> None:
    out = compose(FakeChat(["nope", "still nope", "x", "y"]), "hello")
    assert planted(out) == []
    assert out.warnings


def test_model_failure_propagates() -> None:
    with pytest.raises(LlmError):
        compose(FakeChat([LlmError("APITimeoutError")]), "x")
