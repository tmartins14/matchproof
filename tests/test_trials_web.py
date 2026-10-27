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
    fail_top_of,
    hero_of,
    is_measured,
    live_narrator_of,
    note_of,
    picks_of,
    ranks_of,
    reason_line_of,
    shrink_to_limit,
    trap_label,
    trap_record_of,
    trim,
    word_diff,
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
        "reason_bucket": "overclaim",
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
        "note": "overclaim: Because.",
    }


def test_worst_orders_amended_below_held() -> None:
    rows = [
        claim("HELD", 10, "bt-1"),
        claim("AMENDED", 50, "bt-2"),
        claim("STANDS", 60, "bt-3"),
    ]
    got = worst_of(rows, "a")
    assert got and got["beat"] == "bt-2"


def test_on_a_tie_a_code_caught_claim_beats_a_judge_caught_one() -> None:
    rows = [
        claim("OVERTURNED", 90, "bt-late", reason_bucket="overclaim"),
        claim("OVERTURNED", 40, "bt-numbers", reason_bucket="numbers"),
        claim("OVERTURNED", 30, "bt-names", reason_bucket="names"),
    ]
    got = worst_of(rows, "a")
    assert got and got["beat"] == "bt-numbers"  # code first, then the latest of those


def test_trap_claims_come_first_unless_they_all_stand() -> None:
    traps = frozenset({("fx-01", "bt-trap")})
    rows = [
        claim("OVERTURNED", 90, "bt-other"),
        claim("AMENDED", 20, "bt-trap"),
    ]
    got = worst_of(rows, "a", traps)
    assert got and (got["beat"], got["verdict"]) == ("bt-trap", "AMENDED")
    standing = [claim("OVERTURNED", 90, "bt-other"), claim("STANDS", 20, "bt-trap")]
    got = worst_of(standing, "a", traps)
    assert (
        got and got["beat"] == "bt-other"
    )  # every trap claim stands: all scored claims


def test_unscored_rows_and_other_candidates_are_ignored() -> None:
    rows = [
        claim("OVERTURNED", 99, "bt-9", scored=False),
        claim("OVERTURNED", 99, "bt-8", candidate="b"),
        claim("STANDS", 1, "bt-1"),
    ]
    got = worst_of(rows, "a")
    assert got and got["beat"] == "bt-1"
    assert worst_of(rows, "nobody") is None


def test_note_is_bucket_and_reason_with_the_reviewer_prefix_stripped() -> None:
    judge = claim(
        "OVERTURNED", 1, "bt-1", reasons=["Judge (motive): 'push' is intent."]
    )
    assert note_of(judge) == "overclaim: 'push' is intent."
    second = claim(
        "OVERTURNED",
        1,
        "bt-1",
        reasons=["Second reviewer (wrong_entity): the other side."],
    )
    assert note_of(second) == "overclaim: the other side."
    code = claim(
        "OVERTURNED",
        1,
        "bt-1",
        reasons=["The number 6 matches nothing."],
        reason_bucket="numbers",
    )
    assert note_of(code) == "numbers: The number 6 matches nothing."
    assert note_of(claim("STANDS", 1, "bt-1", reasons=[])) == "Text."


def test_note_says_citation_reasons_in_plain_english_with_no_fact_id() -> None:
    not_given = claim(
        "OVERTURNED",
        1,
        "bt-1",
        reasons=["Cited fact fx-000123 is not in the beat's fact bundle."],
        reason_bucket="citation",
    )
    assert note_of(not_given) == "citation: cited a fact it wasn't given"
    unknown = claim(
        "OVERTURNED",
        1,
        "bt-1",
        reasons=["Unknown fact id fx-nope."],
        reason_bucket="citation",
    )
    assert note_of(unknown) == "citation: cited a fact that doesn't exist"
    for row in (not_given, unknown):
        assert "fx-" not in note_of(row)


def test_note_uses_the_reason_that_matches_the_bucket() -> None:
    both = claim(
        "OVERTURNED",
        1,
        "bt-1",
        reasons=[
            "Cited fact fx-9 is not in the beat's fact bundle.",
            'The number "6" matches no display rendering of the cited facts.',
        ],
        reason_bucket="numbers",
    )
    assert note_of(both).startswith("numbers: The number")


def test_note_is_cut_at_a_word_boundary_near_90_characters() -> None:
    text = "word " * 60
    got = trim(text)
    assert got.endswith("…") and 80 <= len(got) <= 91
    assert not got[:-1].endswith("wor")  # never mid-word
    assert trim("short") == "short"


def test_trap_record_counts_scored_trap_claims_only() -> None:
    traps = frozenset({("fx-01", "bt-t1"), ("fx-01", "bt-t2")})
    rows = [
        claim("STANDS", 1, "bt-t1"),
        claim("OVERTURNED", 2, "bt-t2"),
        claim("OVERTURNED", 3, "bt-t2", scored=False),
        claim("OVERTURNED", 4, "bt-x"),
        claim("HELD", 5, "bt-t1", candidate="b"),
    ]
    assert trap_record_of(rows, "a", traps) == {
        "STANDS": 1,
        "AMENDED": 0,
        "OVERTURNED": 1,
        "HELD": 0,
    }


def test_fail_top_is_the_biggest_bucket() -> None:
    assert fail_top_of({"numbers": 0.2, "overclaim": 0.8}) == {
        "bucket": "overclaim",
        "share": 0.8,
    }
    assert fail_top_of({}) is None


def test_sole_pick_is_set_only_when_one_measured_candidate_is_cleared() -> None:
    one = picks_of(
        [row("mini", p90_ms=2700, usd_per_match=0.017), row("nano", cleared=False)]
    )
    assert one["sole"] == {"candidate": "mini", "p90_ms": 2700, "usd_per_match": 0.017}
    many = picks_of([row("a"), row("b")])
    assert many["sole"] is None
    unpriced = picks_of([row("free", usd_per_match="prices not set")])
    assert unpriced["sole"] and unpriced["sole"]["usd_per_match"] is None
    assert picks_of([row("grok", held=68)])["sole"] is None  # unmeasured does not count


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
        "sole": None,
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


@pytest.mark.parametrize(
    ("kind", "note", "clock", "label"),
    [
        ("red_card", "Which side is down to ten.", "61′", "RED CARD 61′"),
        (
            "penalty",
            "The stoppage-time penalty makes it 3–3.",
            "90+8′",
            "STOPPAGE-TIME PENALTY 90+8′",
        ),
        ("penalty", "Who took it and who scored.", "9′", "PENALTY 9′"),
        (
            "high_turnover_goal",
            "A winner in 90 to 95 minutes.",
            "90+7′",
            "LATE WINNER 90+7′",
        ),
        (
            "open_play_goal",
            "3–2: the lead changes hands at the end.",
            "90+3′",
            "LATE WINNER 90+3′",
        ),
        (
            "set_piece_goal",
            "The equaliser flips the scoreline.",
            "55′",
            "EQUALISER 55′",
        ),
        ("counter_goal", "Ashford level at 1–1 on the break.", "27′", "EQUALISER 27′"),
        ("counter_goal", "0–2: the score and who leads.", "36′", "COUNTER GOAL 36′"),
        (
            "set_piece_goal",
            "1–2: Rivermouth are still behind.",
            "70′",
            "SET-PIECE GOAL 70′",
        ),
        ("open_play_goal", "The second goal against ten men.", "78′", "GOAL 78′"),
    ],
)
def test_trap_label(kind: str, note: str, clock: str, label: str) -> None:
    assert trap_label(kind, note, clock) == label


def test_every_pack_trap_kind_has_a_name() -> None:
    _, fixtures = load_pack(PACK_PATH)
    for fixture in fixtures:
        for trap in fixture.traps:
            assert trap_label(trap["kind"], trap["note"], "1′").endswith(" 1′")


def test_a_trap_beat_resolves_for_every_pack_fixture(web: dict[str, Any]) -> None:
    _, fixtures = load_pack(PACK_PATH)
    by_id = {f["id"]: f for f in web["fixtures"]}
    assert sorted(by_id) == [f.id for f in fixtures]
    for fixture in fixtures:
        row_ = by_id[fixture.id]
        assert len(row_["trap_beats"]) == len(fixture.traps)
        for trap, beat in zip(row_["traps"], row_["trap_beats"], strict=True):
            assert beat["event_id"] == trap["event_id"]
            assert "′" in trap["label"]
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


def test_every_candidate_has_a_trap_record_and_a_fail_top(web: dict[str, Any]) -> None:
    traps = {(f["id"], t["beat"]) for f in web["fixtures"] for t in f["trap_beats"]}
    for c in web["results"]["summary"]:
        name = c["candidate"]
        scored = [
            x
            for x in web["results"]["claims"]
            if x["candidate"] == name
            and x["scored"]
            and (x["fixture"], x["beat"]) in traps
        ]
        assert sum(web["trap_record"][name].values()) == len(scored)
        assert (web["fail_top"][name] is None) == (not c["fail_profile"])


def test_a_measured_worst_is_on_a_trap_beat_when_any_trap_failed(
    web: dict[str, Any],
) -> None:
    traps = {(f["id"], t["beat"]) for f in web["fixtures"] for t in f["trap_beats"]}
    for name, w in web["worst"].items():
        if w is None:
            continue
        record = web["trap_record"][name]
        if record["STANDS"] < sum(record.values()):  # some trap claim did not stand
            assert (w["fixture"], w["beat"]) in traps


def test_claim_numbers_tie_each_number_to_a_fact_the_row_cites() -> None:
    web = json.loads(
        (ROOT / "apps" / "web" / "fixtures" / "trials" / "web-pack-v1.json").read_text(
            "utf-8"
        )
    )
    claims, numbers = web["results"]["claims"], web["claim_numbers"]
    assert set(numbers) == {str(i) for i in range(len(claims))}
    for i, c in enumerate(claims):
        assert {n["fact_id"] for n in numbers[str(i)]} <= set(c["fact_ids"])
    assert any(numbers.values())


def test_word_diff_marks_only_the_words_that_changed() -> None:
    ops = word_diff("Ashford are down to nine men", "Ashford are down to ten men")
    assert ops == [
        {"op": "equal", "text": "Ashford are down to "},
        {"op": "delete", "text": "nine"},
        {"op": "insert", "text": "ten"},
        {"op": "equal", "text": " men"},
    ]
    assert word_diff("same words", "same words") == [
        {"op": "equal", "text": "same words"}
    ]


def test_claim_diff_rebuilds_the_draft_and_the_aired_text_of_every_amended_claim() -> (
    None
):
    web = json.loads(
        (ROOT / "apps" / "web" / "fixtures" / "trials" / "web-pack-v1.json").read_text(
            "utf-8"
        )
    )
    claims, diffs = web["results"]["claims"], web["claim_diff"]
    amended = {
        str(i)
        for i, c in enumerate(claims)
        if c["verdict"] == "AMENDED" and c["lost"] is None
    }
    assert amended and set(diffs) == amended
    for i in amended:
        ops = diffs[i]
        assert (
            "".join(o["text"] for o in ops if o["op"] != "insert")
            == claims[int(i)]["draft_text"]
        )
        assert (
            "".join(o["text"] for o in ops if o["op"] != "delete")
            == claims[int(i)]["text"]
        )


def test_the_tables_note_is_the_compare_reason_cut_to_length() -> None:
    web = json.loads(
        (ROOT / "apps" / "web" / "fixtures" / "trials" / "web-pack-v1.json").read_text(
            "utf-8"
        )
    )
    claims, reasons = web["results"]["claims"], web["claim_reason"]
    assert set(reasons) == {
        str(i) for i, c in enumerate(claims) if reason_line_of(c) is not None
    }
    for name, w in web["worst"].items():
        if w is None:
            continue
        i = next(
            i
            for i, c in enumerate(claims)
            if (c["candidate"], c["fixture"], c["beat"], c["scored"])
            == (name, w["fixture"], w["beat"], True)
        )
        if str(i) in reasons:
            assert reasons[str(i)].startswith(w["note"].rstrip("…"))


def summary_row(
    candidate: str, *, cleared: bool, pts: int, held: int = 0
) -> dict[str, Any]:
    return {
        "candidate": candidate,
        "claims": 10,
        "held": held,
        "cleared": cleared,
        "pts": pts,
        "usd_per_match": 0.01,
        "p90_ms": 1000,
    }


def hero_record(overturned: dict[str, int]) -> dict[str, Any]:
    return {
        k: {"STANDS": 14 - o, "AMENDED": 0, "OVERTURNED": o, "HELD": 0}
        for k, o in overturned.items()
    }


def test_hero_names_the_sole_cleared_and_the_worst_uncleared() -> None:
    summary = [
        summary_row("a", cleared=True, pts=100),
        summary_row("b", cleared=False, pts=-5),
        summary_row("c", cleared=False, pts=-50),
        summary_row("d", cleared=False, pts=-90, held=9),  # unmeasured: never the worst
    ]
    got = hero_of(summary, hero_record({"a": 3, "b": 8, "c": 8, "d": 14}))
    assert got == {
        "cleared": ["a"],
        "sole": {"candidate": "a", "overturned": 3, "total": 14},
        "fewest": None,
        "worst": {
            "candidate": "c",
            "overturned": 8,
            "total": 14,
        },  # ties go to fewer points
    }


def test_hero_is_null_with_nobody_cleared() -> None:
    assert hero_of([], {}) is None
    summary = [summary_row("a", cleared=False, pts=-5)]
    assert hero_of(summary, hero_record({"a": 9})) is None
    unmeasured = [summary_row("a", cleared=True, pts=300, held=20)]
    assert hero_of(unmeasured, hero_record({"a": 0})) is None


def test_hero_lists_three_cleared_in_rank_order_and_the_one_with_fewest_traps() -> None:
    summary = [
        summary_row("a", cleared=True, pts=300),
        summary_row("b", cleared=True, pts=200),
        summary_row("c", cleared=True, pts=100),
        summary_row("d", cleared=False, pts=-5),
    ]
    got = hero_of(summary, hero_record({"a": 4, "b": 1, "c": 1, "d": 9}))
    assert got == {
        "cleared": ["a", "b", "c"],
        "sole": None,
        "fewest": {
            "candidate": "b",
            "overturned": 1,
            "total": 14,
        },  # a tie goes to the higher rank
        "worst": {"candidate": "d", "overturned": 9, "total": 14},
    }


def test_trap_verdicts_cover_every_trap_of_every_fixture(web: dict[str, Any]) -> None:
    traps = {f["id"]: f["traps"] for f in web["fixtures"]}
    for cand, by_fixture in web["trap_verdicts"].items():
        assert set(by_fixture) == set(traps), cand
        for fid, rows in by_fixture.items():
            assert [r["label"] for r in rows] == [t["label"] for t in traps[fid]]
            assert all(r["beat"] in web["moments"][fid] and r["clock"] for r in rows)
    record = web["trap_record"]
    for cand, by_fixture in web["trap_verdicts"].items():
        n = sum(len(rows) for rows in by_fixture.values())
        assert n == sum(record[cand].values())
