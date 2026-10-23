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
}


def test_mix_is_38_bad_and_14_good() -> None:
    counts = Counter(c["kind"] for c in CLAIMS)
    assert counts == {
        "wrong_number": 7,
        "uncited_number": 5,
        "overclaim": 6,
        "invented_cause": 4,
        "wrong_entity": 3,
        "wrong_minute": 2,
        "outside_knowledge": 3,
        "motive": 8,
        "good": 14,
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
    in_bundle = {f.root for f in beat.fact_ids}
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
        [Score("a", 35, 0, 3000), Score("b", 36, 1, 3900), Score("c", 36, 1, 3500)]
    )
    assert (pick.deployment, pick.fallback) == ("c", False)


def test_pick_skips_candidates_that_miss_any_threshold() -> None:
    scores = [
        Score("few", 34, 0, 1000),
        Score("blocks", 38, 2, 1000),
        Score("slow", 38, 0, 4001),
    ]
    pick = pick_judge(scores)
    assert pick.fallback and pick.deployment == "gpt-5-mini"
    assert pick_judge([Score("edge", 35, 1, 4000)]).deployment == "edge"


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
    assert (MIN_CAUGHT, MAX_GOOD_BLOCKED) == (35, 1)


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
