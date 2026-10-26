"""Narrator Trials web export: ranks, worst moments, picks and the built file. No model calls."""

import json
from pathlib import Path
from typing import Any

import pytest
from agents.llm_client import load_models
from contracts.models import TrialsWeb

from evals.trials import PACK_PATH, load_pack
from evals.trials_web import (
    build_web,
    is_measured,
    live_narrator_of,
    picks_of,
    ranks_of,
    shrink_to_limit,
    worst_of,
)

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "evals" / "reports" / "trials" / "pack-v1.json"


def row(name: str, **extra: Any) -> dict[str, Any]:
    return {
        "candidate": name,
        "claims": 85,
        "held": 0,
        "cleared": True,
        "p90_ms": 3000,
        "usd_per_match": 0.02,
        **extra,
    }


def claim(verdict: str, minute: int, beat: str, **extra: Any) -> dict[str, Any]:
    return {
        "candidate": "a",
        "fixture": "fx-01",
        "beat": beat,
        "minute": minute,
        "scored": True,
        "verdict": verdict,
        "reasons": ["Because."],
        "failed_span": None,
        "corrected_span": None,
        "text": "Text.",
        **extra,
    }


def test_measured_is_held_share_at_most_a_tenth() -> None:
    assert is_measured(row("a", claims=85, held=8)) is True  # 9.4%
    assert is_measured(row("a", claims=85, held=9)) is False  # 10.6%
    assert is_measured(row("a", claims=80, held=8)) is True  # exactly 10%
    assert is_measured(row("a", claims=0, held=0)) is False


def test_ranks_and_order_skip_unmeasured_rows() -> None:
    summary = [row("a"), row("grok", held=68), row("b"), row("phi", held=23)]
    ranks, order = ranks_of(summary)
    assert ranks == {"a": 1, "b": 2}
    assert order == ["a", "b", "grok", "phi"]


def test_worst_is_the_lowest_verdict_and_the_latest_on_a_tie() -> None:
    rows = [
        claim("STANDS", 90, "bt-3"),
        claim("OVERTURNED", 20, "bt-1"),
        claim("OVERTURNED", 70, "bt-2"),
        claim("AMENDED", 80, "bt-4"),
    ]
    assert worst_of(rows, "a") == {
        "fixture": "fx-01",
        "beat": "bt-2",
        "verdict": "OVERTURNED",
        "note": "Because.",
    }


def test_worst_orders_amended_below_held_and_shows_the_span() -> None:
    rows = [
        claim("HELD", 10, "bt-1"),
        claim("AMENDED", 50, "bt-2", failed_span="nine", corrected_span="ten"),
        claim("STANDS", 60, "bt-3"),
    ]
    got = worst_of(rows, "a")
    assert got and (got["beat"], got["note"]) == ("bt-2", "nine → ten")
    only_stands = worst_of([claim("STANDS", 5, "bt-1", reasons=[])], "a")
    assert only_stands and only_stands["note"] == "Text."


def test_unscored_rows_and_other_candidates_are_ignored() -> None:
    rows = [
        claim("OVERTURNED", 99, "bt-9", scored=False),
        claim("OVERTURNED", 99, "bt-8", candidate="b"),
        claim("STANDS", 1, "bt-1"),
    ]
    got = worst_of(rows, "a")
    assert got and got["beat"] == "bt-1"
    assert worst_of(rows, "nobody") is None


def test_note_is_trimmed_to_110_characters() -> None:
    got = worst_of([claim("OVERTURNED", 1, "bt-1", reasons=["x" * 300])], "a")
    assert got and len(got["note"]) == 110 and got["note"].endswith("…")


def test_picks_use_measured_cleared_rows_and_never_an_unpriced_budget() -> None:
    summary = [
        row("mini", p90_ms=2700, usd_per_match=0.017),
        row("nano", cleared=False, p90_ms=100),
        row("free", p90_ms=4000, usd_per_match="prices not set"),
        row(
            "grok", held=68, p90_ms=1, usd_per_match=0.001
        ),  # fast and cheap, unmeasured
    ]
    picks = picks_of(summary)
    assert picks["live_feed"] == {"candidate": "mini", "p90_ms": 2700}
    assert picks["budget"] == {"candidate": "mini", "usd_per_match": 0.017}
    assert picks["not_cleared"] == ["nano"]


def test_picks_are_null_when_nothing_qualifies() -> None:
    assert picks_of([row("grok", held=68)]) == {
        "live_feed": None,
        "budget": None,
        "not_cleared": None,
    }
    only_unpriced = picks_of([row("free", usd_per_match="prices not set")])
    assert only_unpriced["budget"] is None
    assert only_unpriced["live_feed"] is not None


def test_live_narrator_is_the_candidate_on_the_models_yaml_deployment() -> None:
    candidates = [
        {"id": "gpt-5-mini", "deployment": "gpt-5-mini"},
        {"id": "grok-4.7", "deployment": "judge-grok"},
    ]
    assert live_narrator_of(candidates, "judge-grok") == "grok-4.7"
    assert live_narrator_of(candidates, "gpt-4o") is None
    assert live_narrator_of(candidates, load_models()["narrator"]["deployment"]) == (
        "gpt-5-mini"
    )


def test_shrink_keeps_trap_and_worst_freeze_frames() -> None:
    frame = {"x": "y" * 500}
    web: dict[str, Any] = {
        "fixtures": [{"id": "fx-01", "trap_beats": [{"beat": "bt-t"}]}],
        "worst": {"a": {"fixture": "fx-01", "beat": "bt-w"}, "grok": None},
        "moments": {
            "fx-01": {b: {"freeze": frame} for b in ("bt-t", "bt-w", "bt-other")}
        },
    }
    assert shrink_to_limit(web, limit=10**9) == []
    assert shrink_to_limit(web, limit=100) == ["fx-01/bt-other"]
    assert web["moments"]["fx-01"]["bt-other"]["freeze"] is None
    assert web["moments"]["fx-01"]["bt-t"]["freeze"] == frame


@pytest.fixture(scope="module")
def web() -> dict[str, Any]:
    _, fixtures = load_pack(PACK_PATH)
    results = json.loads(RESULTS.read_text("utf-8"))
    return build_web(
        results, fixtures, str(load_models()["narrator"]["deployment"]), []
    )


def test_a_trap_beat_resolves_for_every_pack_fixture(web: dict[str, Any]) -> None:
    _, fixtures = load_pack(PACK_PATH)
    by_id = {f["id"]: f for f in web["fixtures"]}
    assert sorted(by_id) == [f.id for f in fixtures]
    for fixture in fixtures:
        row_ = by_id[fixture.id]
        assert len(row_["trap_beats"]) == len(fixture.traps)
        for trap, beat in zip(row_["traps"], row_["trap_beats"], strict=True):
            assert beat["event_id"] == trap["event_id"]
            assert beat["beat"] in web["moments"][fixture.id]


def test_the_export_validates_against_its_schema(web: dict[str, Any]) -> None:
    TrialsWeb.model_validate(web)


def test_every_scored_beat_has_a_moment_and_a_clock(web: dict[str, Any]) -> None:
    claims = web["results"]["claims"]
    for i, c in enumerate(claims):
        assert c["beat"] in web["moments"][c["fixture"]]
        assert (
            web["claim_clock"][str(i)]
            == web["moments"][c["fixture"]][c["beat"]]["clock"]
        )


def test_unmeasured_candidates_have_no_rank_or_worst(web: dict[str, Any]) -> None:
    for name, ok in web["measured"].items():
        assert (name in web["ranks"]) is ok
        assert (web["worst"][name] is not None) is ok
    assert web["order"][: len(web["ranks"])] == sorted(
        web["ranks"], key=web["ranks"].get
    )
