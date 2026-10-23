"""The adversarial claims file and the judge pick rule. No model calls."""

import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
import yaml
from agents.reconcile import reconcile
from intel.voice_lint import lint

from evals.golden import bundle_fact_ids
from evals.pick import Score, pick_judge, set_active_judge

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "intel" / "tests"))
from matches import lean  # type: ignore[import-not-found]

CLAIMS: list[dict[str, Any]] = yaml.safe_load(
    (ROOT / "evals" / "adversarial" / "claims.yaml").read_text("utf-8")
)
# Bad claims the code checks must stop; every other bad claim must reach the judge.
CODE_KINDS = {"wrong_number", "uncited_number"}
CODE_IDS = {
    "adv-27",  # a wrong minute written as a number
    "adv-16",  # "clinical": the evaluative-adjective voice rule now stops it before the judge
    "adv-39",  # "smart": the same rule
    "adv-43",  # "composed": the same rule
    "adv-44",  # "edge in front" with no score or lead fact cited
}


def test_mix_is_44_bad_and_18_good() -> None:
    counts = Counter(c["kind"] for c in CLAIMS)
    assert counts == {
        "wrong_number": 7,
        "uncited_number": 5,
        "overclaim": 11,
        "invented_cause": 5,
        "wrong_entity": 3,
        "wrong_minute": 2,
        "outside_knowledge": 3,
        "motive": 8,
        "good": 18,
    }
    assert {c["expected"] for c in CLAIMS if c["kind"] == "good"} == {"verified"}
    assert {c["expected"] for c in CLAIMS if c["kind"] != "good"} <= {
        "blocked",
        "rephrased",
    }


@pytest.mark.parametrize("claim", CLAIMS, ids=[c["id"] for c in CLAIMS])
def test_code_checks_stop_exactly_the_claims_meant_for_them(
    claim: dict[str, Any],
) -> None:
    m = lean(claim["match"]["story"], claim["match"]["seed"])
    beat = next(b for b in m.beats if b.id.root == claim["beat_id"])
    in_bundle = set(bundle_fact_ids(m.registry, beat))
    assert set(claim["fact_ids"]) <= in_bundle
    facts = {fid: m.registry.get(fid) for fid in in_bundle}
    rec = reconcile(claim["text"], claim["fact_ids"], facts)
    errors = [v for v in lint(claim["text"], "narration") if v.severity == "error"]
    by_code = not rec.ok or bool(errors)
    meant_for_code = claim["kind"] in CODE_KINDS or claim["id"] in CODE_IDS
    if claim["kind"] == "good":
        assert not by_code, (rec.reasons, errors)
        assert len(claim["text"].split()) <= 30
    else:
        assert by_code == meant_for_code, (claim["id"], rec.reasons, errors)


def test_pick_takes_most_caught_then_lower_p90() -> None:
    pick = pick_judge(
        [Score("a", 41, 0, 3000), Score("b", 42, 1, 3900), Score("c", 42, 1, 3500)]
    )
    assert (pick.deployment, pick.fallback) == ("c", False)


def test_pick_skips_candidates_that_miss_any_threshold() -> None:
    scores = [
        Score("few", 40, 0, 1000),
        Score("blocks", 44, 2, 1000),
        Score("slow", 44, 0, 4001),
    ]
    pick = pick_judge(scores)
    assert pick.fallback and pick.deployment == "gpt-5-mini"
    assert pick_judge([Score("edge", 41, 1, 4000)]).deployment == "edge"


def test_set_active_judge_rewrites_only_the_judge_block(tmp_path: Path) -> None:
    text = (ROOT / "packages" / "agents" / "config" / "models.yaml").read_text("utf-8")
    path = tmp_path / "models.yaml"
    path.write_text(text, "utf-8")
    set_active_judge(path, "judge-grok")
    new = yaml.safe_load(path.read_text("utf-8"))
    assert new["judge"]["deployment"] == "judge-grok"
    assert (
        new["judge"]["response_format"] == "json_schema"
        and new["judge"]["temperature"] == 0
    )
    assert new["narrator"] == yaml.safe_load(text)["narrator"]
    assert new["judge_candidates"] == yaml.safe_load(text)["judge_candidates"]
    assert path.read_text("utf-8").startswith("# Model deployments by role")


def test_the_golden_matches_are_built_with_the_roster() -> None:
    from evals.golden import build_store

    store, match_id = build_store("red_card_flip", 3)
    shooters = [
        f for f in store.registry(match_id).all() if f.name.endswith(".shooter")
    ]
    assert shooters
    for f in shooters:
        assert not re.fullmatch(r"(home|away)-\d{2}", str(f.value)), f.value
    assert any(f.value == "Pryce" for f in shooters)


def test_the_file_counts_match_the_pick_rule_denominators() -> None:
    from evals.pick import BAD_TOTAL, GOOD_TOTAL, MAX_GOOD_BLOCKED, MIN_CAUGHT

    bad = [c for c in CLAIMS if c["kind"] != "good"]
    assert (len(bad), len(CLAIMS) - len(bad)) == (BAD_TOTAL, GOOD_TOTAL)
    assert (MIN_CAUGHT, MAX_GOOD_BLOCKED) == (41, 1)


def test_the_card_label_names_the_player_from_the_roster() -> None:
    from intel.labels import LabelContext, label_for

    from evals.golden import build_store

    store, match_id = build_store("red_card_flip", 3)
    registry = store.registry(match_id)
    ctx = LabelContext(
        {"home": "Rivermouth", "away": "Ashford Vale"},
        {e.id.root: e for e in store.events(match_id)},
        registry,
    )
    player = registry.by_name("card(ev-001484).player")
    assert not re.fullmatch(r"(home|away)-\d{2}", str(player.value))
    assert label_for(registry.by_name("card(ev-001484).kind"), ctx) == (
        f"{player.value}, second yellow, sent off"
    )


def test_from_audit_turns_a_disagreement_into_a_valid_eval_entry() -> None:
    from evals.from_audit import entries

    audit = {
        "match_id": "m-red-card-flip-3",
        "disagreements": [
            {
                "claim_id": "cl-001997-open_play_goal-01",
                "beat_id": "bt-001997-open_play_goal",
                "fact_ids": ["fx-shot-ev-001997-shooter", "fx-shot-ev-001997-outcome"],
                "text": 'Pryce scores, a "smart" finish.',
                "verdict": "verified",
                "checker": {"deployment": "gpt-5-mini", "reason": "Matches."},
                "auditor": {
                    "deployment": "judge-grok",
                    "problem": "overclaim",
                    "reason": "Smart is evaluative.",
                },
            },
            {
                "claim_id": "cl-001484-momentum_swing-01",
                "beat_id": "bt-001484-momentum_swing",
                "fact_ids": ["fx-a"],
                "text": "Cause claim.",
                "verdict": "rephrased",
                "checker": {"deployment": "gpt-5-mini", "reason": ""},
                "auditor": {
                    "deployment": "judge-grok",
                    "problem": "unsupported_cause",
                    "reason": "No cause fact.",
                },
            },
        ],
    }
    text = entries(audit, 45)
    parsed = yaml.safe_load(text)
    assert [c["id"] for c in parsed] == ["adv-45", "adv-46"]
    first = parsed[0]
    assert first["kind"] == "overclaim" and first["expected"] == "rephrased"
    assert first["match"] == {"story": "red_card_flip", "seed": 3}
    assert first["beat_id"] == "bt-001997-open_play_goal"
    assert first["fact_ids"] == [
        "fx-shot-ev-001997-shooter",
        "fx-shot-ev-001997-outcome",
    ]
    assert first["text"] == 'Pryce scores, a "smart" finish.'
    assert parsed[1]["kind"] == "invented_cause"
    keys = {"id", "kind", "match", "beat_id", "text", "fact_ids", "expected"}
    assert all(set(c) == keys for c in parsed)
