from agents.checker import Checker
from agents.narrator import DraftClaim, Revision
from fakes import TEAMS, FakeChat, bundle_of, fact, timeout

DROP = fact(
    "fx-drop",
    "8 m",
    "8 metres",
    side="home",
    name="back_line_change(home, ev-000001, to t10.00)",  # a change fact: "deeper" compares
)
BUNDLE = bundle_of(DROP)
GOOD = {"supported": True, "problem": None, "reason": "Matches."}
BAD = {
    "supported": False,
    "problem": "unsupported_cause",
    "reason": "No fact says tired.",
}


def draft(text: str, *ids: str) -> DraftClaim:
    return DraftClaim(text=text, fact_ids=list(ids or ["fx-drop"]))


def run(
    judge: FakeChat, drafts: list[DraftClaim], retried: list[DraftClaim] | None = None
):
    asked: list[Revision] = []

    def renarrate(revision: Revision) -> list[DraftClaim]:
        asked.append(revision)
        return retried or []

    out = Checker(judge, max_workers=1).check_beat(
        drafts,
        BUNDLE,
        beat_id="bt-001484-card",
        lang="en",
        teams=TEAMS,
        beat_kind="momentum_swing",
        beat_label="55–70′",
        renarrate=renarrate,
    )
    return out, asked


def test_pass_is_verified() -> None:
    judge = FakeChat([GOOD])
    (c,), asked = run(judge, [draft("Ashford are defending 8 m deeper.")])
    assert c.claim.verdict.value == "verified" and not asked
    assert c.claim.id.root == "cl-001484-card-01"
    assert c.claim.checker is not None and c.claim.checker.reconciled
    assert c.claim.checker.judge_supported and c.claim.checker.retries == 0
    assert [(n.as_written, n.fact_id.root) for n in c.claim.numbers] == [
        ("8 m", "fx-drop")
    ]


def test_fail_then_pass_is_rephrased_and_keeps_the_draft() -> None:
    judge = FakeChat([BAD, GOOD])
    (c,), asked = run(
        judge,
        [draft("Ashford look tired and drop 8 m.")],
        [draft("Ashford are defending 8 m deeper.")],
    )
    assert c.claim.verdict.value == "rephrased"
    assert c.claim.draft_text == "Ashford look tired and drop 8 m."
    assert c.claim.text == "Ashford are defending 8 m deeper."
    assert c.claim.reason is not None and "No fact says tired" in c.claim.reason
    assert c.claim.checker is not None and c.claim.checker.retries == 1
    assert len(asked) == 1 and "No fact says tired" in asked[0].reasons[0]


def test_fail_twice_is_blocked() -> None:
    judge = FakeChat([BAD, BAD])
    (c,), _ = run(
        judge, [draft("Ashford look tired.")], [draft("Ashford look exhausted.")]
    )
    assert c.claim.verdict.value == "blocked"
    assert c.claim.draft_text == "Ashford look tired."
    assert c.claim.reason and "No fact says tired" in c.claim.reason


def test_judge_timeout_is_delayed_and_not_retried() -> None:
    judge = FakeChat([timeout()])
    (c,), asked = run(judge, [draft("Ashford are defending 8 m deeper.")])
    assert c.claim.verdict.value == "delayed" and not asked


def test_failed_reconciliation_never_reaches_the_judge() -> None:
    judge = FakeChat([GOOD])  # would be used by the retry only
    (c,), asked = run(
        judge,
        [draft("Ashford drop 9 m deeper.")],
        [draft("Ashford drop 8 m deeper.")],
    )
    assert len(judge.prompts) == 1  # only the revised claim was judged
    assert "9 m" not in judge.prompts[0]
    assert c.claim.verdict.value == "rephrased" and '"9 m"' in asked[0].reasons[0]


def test_failed_reconciliation_twice_makes_no_judge_call() -> None:
    judge = FakeChat([])
    (c,), _ = run(judge, [draft("Ashford drop 9 m.")], [draft("Ashford drop 10 m.")])
    assert judge.prompts == [] and c.claim.verdict.value == "blocked"


def test_voice_lint_error_fails_before_the_judge() -> None:
    judge = FakeChat([])
    (c,), _ = run(
        judge,
        [draft("Ashford showcase a drop of 8 m.")],
        [draft("Ashford showcase a drop of 8 m.")],
    )
    assert judge.prompts == [] and c.claim.verdict.value == "blocked"
    assert c.claim.reason is not None and "showcase" in c.claim.reason


def test_only_the_failed_claim_is_retried() -> None:
    judge = FakeChat([GOOD, BAD, GOOD])
    out, asked = run(
        judge,
        [draft("Ashford drop 8 m."), draft("Ashford look tired.")],
        [draft("Ashford are 8 m deeper.")],
    )
    assert [c.claim.verdict.value for c in out] == ["verified", "rephrased"]
    assert [c.claim.id.root for c in out] == ["cl-001484-card-01", "cl-001484-card-02"]
    assert asked[0].kept == ["Ashford drop 8 m."]


def test_a_retry_that_repeats_an_accepted_claim_is_not_a_fix() -> None:
    judge = FakeChat([GOOD, BAD])
    out, _ = run(
        judge,
        [draft("Ashford drop 8 m."), draft("Ashford look tired.")],
        [draft("Ashford drop 8 m.")],
    )
    assert [c.claim.verdict.value for c in out] == ["verified", "blocked"]


def test_the_judge_prompt_is_the_configured_file() -> None:
    from agents.checker import judge_prompt_path, render_judge_prompt

    assert judge_prompt_path().name == "judge.v3.md"  # config/models.yaml points at v3
    args = ([DROP], TEAMS, "card", "63′")
    v2 = render_judge_prompt("Ashford drop 8 m.", *args)  # the configured file, v3
    assert "Commonly missed" in v2
    v1 = render_judge_prompt("Ashford drop 8 m.", *args, prompt_file="judge.v1.md")
    assert "motive" in v2 and "Allowed without a fact" in v2
    assert "motive" not in v1 and "You are strict" in v1
