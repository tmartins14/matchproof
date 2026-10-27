"""Narrator Trials: verdict mapping, scoring, buckets and the table. No model calls."""

import sys
from pathlib import Path
from typing import Any

import pytest
from agents.checker import JUDGE_REASON_PREFIX, CheckedClaim, ClaimCheck
from agents.llm_client import LlmError, load_models, trial_settings
from agents.pipeline import BeatRun
from agents.reconcile import reconcile
from contracts.models import Audit, Claim, TrialsResults
from intel.voice_lint import lint

from evals.trials import (
    POINTS,
    CauseRecorder,
    MergeError,
    check_pack,
    claim_row,
    differing_span,
    fail_profile,
    is_judge_only,
    load_pack,
    lost_beat,
    markdown,
    merge_results,
    prompt_hash,
    rank,
    reason_bucket,
    referee_split,
    summarize_candidate,
    trial_verdict,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "agents" / "tests"))
from fakes import fact  # type: ignore[import-not-found]

GOAL = fact("fx-goal", "2–0", "two nil", name="score_after(ev-000100)")
RED = fact("fx-red", "60′", name="red_card_minute")
NAMED = fact("fx-who", "Okafor", value="Okafor", name="scorer")  # type: ignore[arg-type]
BUNDLE = {f.id.root: f for f in (GOAL, RED, NAMED)}


def reasons_of(text: str, cites: list[str], names: tuple[str, ...] = ()) -> list[str]:
    return reconcile(text, cites, BUNDLE, names).reasons


def test_verdict_mapping_and_points() -> None:
    assert [
        trial_verdict(v) for v in ("verified", "rephrased", "blocked", "delayed")
    ] == [
        "STANDS",
        "AMENDED",
        "OVERTURNED",
        "HELD",
    ]
    assert POINTS == {"STANDS": 3, "AMENDED": 1, "OVERTURNED": -3, "HELD": 0}


@pytest.mark.parametrize(
    ("reasons", "problem", "bucket"),
    [
        (reasons_of("They lead 3–0.", ["fx-goal"]), None, "numbers"),
        (reasons_of("Haldane scores.", ["fx-goal"], ("Haldane",)), None, "names"),
        (reasons_of("Ashford are down to ten.", []), None, "citation"),
        (reasons_of("Ashford are down to ten.", ["fx-nope"]), None, "citation"),
        ([], "wrong_entity", "attribution"),
        ([], "wrong_time", "timing"),
        (["Judge (motive): says why."], "motive", "overclaim"),
        ([], "outside_knowledge", "overclaim"),
        (reasons_of("Their line is higher.", ["fx-red"]), None, "overclaim"),
        (
            [m.rule_id for m in lint("A dramatic turn of events!", "narration")],
            None,
            "other",
        ),
        (["Judge (unsupported): no."], None, "other"),
    ],
)
def test_reason_buckets(reasons: list[str], problem: str | None, bucket: str) -> None:
    assert reason_bucket(reasons, problem) == bucket


def test_voice_rule_is_wording() -> None:
    from agents.checker import VOICE_REASON_PREFIX

    assert (
        reason_bucket([f'{VOICE_REASON_PREFIX}em-dash broken by "—": no.'], None)
        == "wording"
    )


def test_first_match_wins() -> None:
    both = [*reasons_of("They lead 3–0.", ["fx-goal"]), "Judge (wrong_entity): x"]
    assert reason_bucket(both, "wrong_entity") == "numbers"


def test_differing_span_is_the_shortest_cover() -> None:
    assert differing_span(
        "Ashford are down to nine men now", "Ashford are down to ten men now"
    ) == (
        "nine",
        "ten",
    )
    assert differing_span("same words", "same words") == (None, None)


def claim(verdict: str, n: int = 1, **extra: Any) -> Claim:
    return Claim.model_validate(
        {
            "id": f"cl-000100-card-{n:02d}",
            "beat_id": "bt-000100-card",
            "lang": "en",
            "text": "Ashford are down to ten.",
            "fact_ids": ["fx-red"],
            "numbers": [],
            "verdict": verdict,
            **({"reason": "r"} if verdict in ("rephrased", "blocked") else {}),
            **extra,
        }
    )


def checked(c: Claim, reasons: list[str], problem: str | None = None) -> CheckedClaim:
    first = ClaimCheck(c.text, [], reasons=reasons, judge_problem=problem)
    return CheckedClaim(c, first, first)


def test_only_the_first_claim_of_a_beat_is_scored() -> None:
    run = BeatRun([], [], 1900)
    rows = [
        claim_row("fx-01", "m", 60, run, checked(claim("verified", n), []), n - 1)
        for n in (1, 2)
    ]
    assert [r["scored"] for r in rows] == [True, False]


def test_amended_row_carries_bucket_and_span() -> None:
    c = claim("rephrased", draft_text="Ashford are down to nine.")
    row = claim_row(
        "fx-01",
        "m",
        60,
        BeatRun([], [], 5),
        checked(c, reasons_of("Down to 9.", ["fx-red"])),
        0,
    )
    assert (row["verdict"], row["reason_bucket"]) == ("AMENDED", "numbers")
    assert (row["failed_span"], row["corrected_span"]) == ("nine.", "ten.")
    assert row["draft_text"] == "Ashford are down to nine."


def test_consensus_overturn_is_bucketed_from_the_auditor() -> None:
    blocked = claim("blocked", reason="Second reviewer (wrong_entity): the other side.")
    audit = Audit.model_validate(
        {"deployment": "judge-grok", "outcome": "disagree", "problem": "wrong_entity"}
    )
    row = claim_row(
        "fx-01",
        "m",
        60,
        BeatRun([], [], 5),
        checked(claim("verified"), []),
        0,
        audit=audit,
        corrected=blocked,
    )
    assert (row["verdict"], row["reason_bucket"], row["corrected_by_consensus"]) == (
        "OVERTURNED",
        "attribution",
        True,
    )
    assert row["auditor"] == "disagree (wrong_entity)"


def scored(
    candidate: str,
    fixture: str,
    verdict: str,
    bucket: str | None = None,
    agree: str = "agree",
    **extra: Any,
) -> dict[str, Any]:
    return {
        "candidate": candidate,
        "fixture": fixture,
        "scored": True,
        "verdict": verdict,
        "reason_bucket": bucket,
        "auditor": agree,
        **extra,
    }


def test_summary_maths() -> None:
    rows = [
        scored("a", "fx-01", "STANDS"),
        scored("a", "fx-01", "STANDS"),
        scored("a", "fx-01", "AMENDED", "numbers"),
        scored("a", "fx-02", "OVERTURNED", "attribution", "disagree (wrong_entity)"),
        scored("a", "fx-02", "HELD", None, "not audited"),
        {
            **scored("a", "fx-02", "STANDS"),
            "scored": False,
        },  # a second claim: not counted
        scored("b", "fx-01", "STANDS"),
    ]
    usage = {
        "narrator": {"deployment": "gpt-5-mini", "input": 1_000_000, "output": 500_000}
    }
    s = summarize_candidate(
        "a",
        rows,
        ["fx-01", "fx-02"],
        [1000, 2000, 3000],
        [4000, 5000, 6000],
        [usage, usage],
    )
    assert (s["claims"], s["stands"], s["amended"], s["overturned"], s["held"]) == (
        5,
        2,
        1,
        1,
        1,
    )
    assert s["pts"] == 3 + 3 + 1 - 3
    assert s["clean_pct"] == 50.0  # 2 of the 4 that are not held
    assert s["cleared"] is True  # overturned 1 <= amended 1
    assert s["p90_ms"] == 3000  # the narrator's call
    assert s["on_air_p90_ms"] == 6000
    assert (s["lost"], s["double_checked"], s["referee_splits"]) == (0, 0, 0)
    assert s["usd_per_match"] == 1.25  # 0.25 + 2.00 * 0.5
    assert s["tokens_per_match"] == 1_500_000
    assert s["fail_profile"] == {"numbers": 0.5, "attribution": 0.5}
    assert s["form"] == ["A", "H"]  # the last scored claim of each fixture
    assert s["by_fixture"] == {
        "fx-01": {"pts": 7, "clean_pct": 66.7},
        "fx-02": {"pts": -3, "clean_pct": 0.0},
    }
    assert s["audit_agreement"] == 0.8  # every audited claim counts, scored or not


def blocked_by(reasons: list[str], problem: str | None = None) -> CheckedClaim:
    c = claim("blocked")
    first = ClaimCheck(c.text, [], reasons=reasons, judge_problem=problem)
    return CheckedClaim(c, first, first)


def draft_preview() -> Claim:
    return claim("verified", draft_text="Ashford are down to nine.")


def test_rejected_beat_is_one_scored_citation_overturn() -> None:
    exc = ValueError(
        "put_claims rejected claims: [{'index': 0, 'claim_id': 'cl-000100-card-01',"
        " 'accepted': False, 'errors': ['Unknown fact id fx-nope.']}]"
    )
    row = lost_beat("fx-01", "m", "bt-000100-card", 60, [draft_preview()], exc=exc)
    assert (row["lost"], row["verdict"], row["reason_bucket"], row["scored"]) == (
        "rejected",
        "OVERTURNED",
        "citation",
        True,
    )
    assert row["reasons"] == ["Unknown fact id fx-nope."]
    assert row["text"] == "Ashford are down to ten."  # from the captured preview
    assert (row["latency_ms"], row["narrator_ms"], row["auditor"]) == (
        None,
        None,
        "not audited",
    )
    other = ValueError("put_claims rejected claims: [{'errors': ['Too long.']}]")
    assert (
        lost_beat("fx-01", "m", "bt-000100-card", 60, [], exc=other)["reason_bucket"]
        == "other"
    )


def test_rejection_is_classified_before_the_catch_all_value_error() -> None:
    rejected = ValueError("put_claims rejected claims: []")
    other = ValueError("something else broke")
    assert lost_beat("fx-01", "m", "bt-000100-card", 60, [], exc=rejected)["lost"] == (
        "rejected"
    )
    row = lost_beat("fx-01", "m", "bt-000100-card", 60, [], exc=other)
    assert (row["lost"], row["verdict"]) == ("no_answer", "HELD")


def test_stand_in_without_a_preview_is_empty() -> None:
    run = BeatRun([], [], 5)
    row = lost_beat("fx-01", "m", "bt-000100-card", 60, [], run=run)
    assert (row["id"], row["text"], row["fact_ids"], row["lost"]) == (
        "cl-000100-card-01",
        "",
        [],
        "no_claim",
    )
    assert (row["verdict"], row["reason_bucket"]) == ("OVERTURNED", "other")


def test_unreadable_costs_points_and_a_failed_call_does_not() -> None:
    unreadable = lost_beat(
        "fx-01",
        "m",
        "bt-000100-card",
        60,
        [],
        run=BeatRun([], [], 5, error="Narrator: StructuredOutputError"),
    )
    assert (unreadable["lost"], unreadable["verdict"]) == ("unreadable", "OVERTURNED")
    assert unreadable["reason_bucket"] == "other"
    failed = lost_beat(
        "fx-01",
        "m",
        "bt-000100-card",
        60,
        [],
        run=BeatRun([], [], 5, error="Narrator: LlmError"),
    )
    assert (failed["lost"], failed["verdict"], failed["reason_bucket"]) == (
        "no_answer",
        "HELD",
        None,
    )
    raised = lost_beat(
        "fx-01", "m", "bt-000100-card", 60, [], exc=LlmError("APITimeoutError")
    )
    assert (raised["lost"], raised["verdict"]) == ("no_answer", "HELD")


def test_a_no_answer_row_names_the_cause() -> None:
    from_exc = lost_beat(
        "fx-01", "m", "bt-000100-card", 60, [], exc=LlmError("RateLimitError")
    )
    assert from_exc["reasons"] == ["LlmError", "RateLimitError"]
    from_run = lost_beat(
        "fx-01",
        "m",
        "bt-000100-card",
        60,
        [],
        run=BeatRun([], [], 5, error="Narrator: LlmError"),
        cause="APITimeoutError",
    )
    assert from_run["reasons"] == ["LlmError", "APITimeoutError"]
    unknown = lost_beat(
        "fx-01",
        "m",
        "bt-000100-card",
        60,
        [],
        run=BeatRun([], [], 5, error="Narrator: LlmError"),
    )
    assert unknown["reasons"] == ["LlmError"]


def test_the_cause_recorder_keeps_the_last_failure_and_passes_replies_through() -> None:
    class Inner:
        deployment = "d"
        response_format = "none"

        def __init__(self) -> None:
            self.fail: str | None = "APITimeoutError"

        def complete(self, prompt: str, **kwargs: Any) -> str:
            if self.fail:
                raise LlmError(self.fail)
            return "ok"

    inner = Inner()
    rec = CauseRecorder(inner)  # type: ignore[arg-type]
    with pytest.raises(LlmError):
        rec.complete("p")
    assert rec.last_cause == "APITimeoutError"
    inner.fail = None
    assert rec.complete("p") == "ok" and rec.last_cause == "APITimeoutError"


def test_equal_denominators_with_a_lost_beat() -> None:
    lost = lost_beat(
        "fx-01",
        "a",
        "bt-000100-card",
        60,
        [],
        exc=ValueError("put_claims rejected claims: []"),
    )
    clean = {**scored("b", "fx-01", "STANDS"), "lost": None}
    rows = [{**lost, "candidate": "a"}, clean]
    a = summarize_candidate("a", rows, ["fx-01"], [], [], [])
    b = summarize_candidate("b", rows, ["fx-01"], [], [], [])
    assert a["claims"] == b["claims"] == 1
    assert (a["lost"], a["overturned"], b["lost"]) == (1, 1, 0)


def test_judge_only_overturn_is_double_checked() -> None:
    judge = blocked_by([f"{JUDGE_REASON_PREFIX}wrong_entity): the other side."])
    code = blocked_by(
        [*reasons_of("They lead 3–0.", ["fx-goal"]), f"{JUDGE_REASON_PREFIX}x): y"]
    )
    assert is_judge_only(judge) is True
    assert is_judge_only(code) is False
    assert is_judge_only(checked(claim("verified"), [])) is False
    audit = Audit.model_validate({"deployment": "d", "outcome": "agree"})
    row = claim_row(
        "fx-01", "m", 60, BeatRun([], [], 5), judge, 0, audit=audit, double_check=True
    )
    assert (row["referee_split"], row["auditor"], row["verdict"]) == (
        True,
        "supports",
        "OVERTURNED",
    )
    confirm = Audit.model_validate(
        {"deployment": "d", "outcome": "disagree", "problem": "wrong_entity"}
    )
    row = claim_row(
        "fx-01", "m", 60, BeatRun([], [], 5), judge, 0, audit=confirm, double_check=True
    )
    assert (row["referee_split"], row["auditor"]) == (False, "confirms (wrong_entity)")
    gone = Audit.model_validate({"deployment": "d", "outcome": "unavailable"})
    assert referee_split(gone) is None
    plain = claim_row("fx-01", "m", 60, BeatRun([], [], 5), code, 0)
    assert plain["referee_split"] is None


def test_audit_agreement_ignores_double_checks() -> None:
    rows = [
        scored("a", "fx-01", "STANDS"),
        scored("a", "fx-01", "OVERTURNED", "other", "supports", referee_split=True),
        scored(
            "a", "fx-02", "OVERTURNED", "other", "confirms (x)", referee_split=False
        ),
    ]
    s = summarize_candidate("a", rows, ["fx-01", "fx-02"], [], [], [])
    assert s["audit_agreement"] == 1.0
    assert (s["double_checked"], s["referee_splits"]) == (2, 1)


def test_markdown_marks_a_split() -> None:
    import json

    example = json.loads(
        (ROOT / "schemas" / "examples" / "trials_results.min.json").read_text("utf-8")
    )
    example["claims"][0].update(verdict="OVERTURNED", referee_split=True)
    text = markdown(example)
    assert "[split]" in text
    assert "On-air p90" in text and "| Split |" in text


def test_not_cleared_and_unpriced() -> None:
    rows = [scored("a", "fx-01", "OVERTURNED", "other"), scored("a", "fx-01", "STANDS")]
    usage = {"narrator": {"deployment": "gpt-5-nano", "input": 10, "output": 10}}
    s = summarize_candidate("a", rows, ["fx-01"], [5], [9], [usage])
    assert s["cleared"] is False
    assert s["usd_per_match"] == "prices not set"


def test_fail_profile_sums_to_one() -> None:
    rows = [scored("a", "f", "AMENDED", b) for b in ("numbers", "wording", "other")]
    assert sum(fail_profile(rows).values()) == pytest.approx(1.0)
    assert fail_profile([scored("a", "f", "STANDS")]) == {}


def test_rank_by_pts_then_clean_then_p90() -> None:
    def row(name: str, pts: int, clean: float, p90: int) -> dict[str, Any]:
        return {"candidate": name, "pts": pts, "clean_pct": clean, "p90_ms": p90}

    ranked = rank(
        [
            row("slow", 10, 80.0, 900),
            row("fast", 10, 80.0, 100),
            row("top", 12, 50.0, 5),
            row("clean", 10, 90.0, 1),
        ]
    )
    assert [r["candidate"] for r in ranked] == ["top", "clean", "fast", "slow"]


def test_the_pack_is_playable() -> None:
    pack, fixtures = load_pack()
    assert pack == "pack-v1"
    assert [f.id for f in fixtures] == [f"fx-0{n}" for n in range(1, 7)]
    assert (
        check_pack(fixtures) == []
    )  # validate_planted passes, and every trap names its moment
    custom = [f for f in fixtures if f.storyline == "custom"]
    assert [f.id for f in custom] == ["fx-05", "fx-06"]


def test_models_yaml_has_the_candidates() -> None:
    models = load_models()
    ids = [e["id"] for e in models["trial_candidates"]]
    assert ids[:2] == ["gpt-5-mini", "grok-4.7"]
    assert len(ids) >= 3


def test_trial_settings_known_and_unknown() -> None:
    models = load_models()
    s = trial_settings(models, "gpt-5-nano")
    assert (s.deployment, s.response_format, s.reasoning_effort) == (
        "gpt-5-nano",
        "json_schema",
        "minimal",
    )
    assert trial_settings(models, "grok-4.7").deployment == "judge-grok"
    with pytest.raises(LlmError) as err:
        trial_settings(models, "not-a-model")
    assert err.value.cause_name == "UnknownCandidate"


def test_prompt_hash_is_eight_hex() -> None:
    h = prompt_hash()
    assert len(h) == 8 and int(h, 16) >= 0


def test_example_and_markdown_render() -> None:
    import json

    example = json.loads(
        (ROOT / "schemas" / "examples" / "trials_results.min.json").read_text("utf-8")
    )
    TrialsResults.model_validate(example)
    text = markdown(example)
    assert "| 1 | gpt-5-mini | 3 |" in text
    assert "Cleared for air" in text


def merge_pair() -> tuple[dict[str, Any], dict[str, Any]]:
    """The real results file as the target, and a one-candidate run of the same pack and referee."""
    import copy
    import json

    target = json.loads(
        (ROOT / "evals" / "reports" / "trials" / "pack-v1.json").read_text("utf-8")
    )
    donor = next(r for r in target["summary"] if r["candidate"] == "gpt-5-mini")
    entry = next(c for c in target["candidates"] if c["id"] == "gpt-5-mini")
    row = {**copy.deepcopy(donor), "candidate": "newcomer", "pts": 500}
    claims = [
        {**copy.deepcopy(c), "candidate": "newcomer"}
        for c in target["claims"]
        if c["candidate"] == "gpt-5-mini"
    ]
    new = {
        "pack": target["pack"],
        "run_at": "2026-10-27T03:00:00Z",
        "git_sha": "abc1234",
        "referee": {
            **copy.deepcopy(target["referee"]),
            "cost": {"currency": "USD", "total": 0.1, "by_role": {"judge": 0.1}},
        },
        "fixtures": copy.deepcopy(target["fixtures"]),
        "candidates": [{**copy.deepcopy(entry), "id": "newcomer"}],
        "claims": claims,
        "errors": [{"candidate": "newcomer", "fixture": "fx-01", "error": "x"}],
        "summary": [row],
    }
    return target, new


def test_a_merge_changes_only_the_named_candidates() -> None:
    target, new = merge_pair()
    before = {r["candidate"]: r for r in target["summary"]}
    merged = merge_results(target, new)
    after = {r["candidate"]: r for r in merged["summary"]}
    assert set(after) == {*before, "newcomer"}
    for name, r in before.items():
        assert after[name] == r  # numbers do not move
    assert [c for c in merged["claims"] if c["candidate"] != "newcomer"] == target[
        "claims"
    ]
    assert [e for e in merged["errors"] if e["candidate"] != "newcomer"] == target[
        "errors"
    ]
    assert {c["id"] for c in merged["candidates"]} == {
        c["id"] for c in target["candidates"]
    } | {"newcomer"}
    TrialsResults.model_validate(merged)


def test_a_merge_replaces_a_candidate_that_is_already_in_the_file() -> None:
    target, new = merge_pair()
    merged = merge_results(target, new)
    again = {
        **new,
        "run_at": "2026-10-27T04:00:00Z",
        "summary": [{**new["summary"][0], "pts": -5}],
    }
    twice = merge_results(merged, again)
    rows = [r for r in twice["summary"] if r["candidate"] == "newcomer"]
    assert [r["pts"] for r in rows] == [-5]
    assert len([c for c in twice["candidates"] if c["id"] == "newcomer"]) == 1
    assert [m["run_at"] for m in twice["merges"]] == [
        "2026-10-27T03:00:00Z",
        "2026-10-27T04:00:00Z",
    ]


def test_a_merge_recomputes_the_ranks_and_adds_the_cost() -> None:
    target, new = merge_pair()
    merged = merge_results(target, new)
    assert merged["summary"][0]["candidate"] == "newcomer"  # 500 pts beats everyone
    assert [r["pts"] for r in merged["summary"]] == sorted(
        (r["pts"] for r in merged["summary"]), reverse=True
    )
    assert merged["referee"]["cost"]["total"] == pytest.approx(
        target["referee"]["cost"]["total"] + 0.1
    )
    assert merged["referee"]["cost"]["by_role"]["judge"] == pytest.approx(
        target["referee"]["cost"]["by_role"]["judge"] + 0.1
    )
    assert merged["merges"] == [
        {
            "candidates": ["newcomer"],
            "run_at": "2026-10-27T03:00:00Z",
            "git_sha": "abc1234",
        }
    ]


def test_a_merge_refuses_a_different_referee_or_pack() -> None:
    target, new = merge_pair()
    for key, value in (
        ("judge", "gpt-4.1"),
        ("auditor", "other"),
        ("judge_prompt", "judge.v4.md"),
        ("audited", False),
    ):
        bad = {**new, "referee": {**new["referee"], key: value}}
        with pytest.raises(MergeError, match="referee"):
            merge_results(target, bad)
    moved = {
        **new,
        "fixtures": [{**new["fixtures"][0], "seed": 999}, *new["fixtures"][1:]],
    }
    with pytest.raises(MergeError, match="pack"):
        merge_results(target, moved)
