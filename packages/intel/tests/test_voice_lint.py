import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from intel.voice_lint import Scope, lint, load_rules, numbers_in

ROOT = Path(__file__).resolve().parents[3]
RULES = load_rules()


def ids(text: str, scope: Scope) -> set[str]:
    return {v.rule_id for v in lint(text, scope, RULES)}


# (rule id, text that fires, near-miss that stays quiet)
CASES: list[tuple[str, str, str]] = [
    ("em-dash", "Ashford level it — at last.", "Ashford level it - at last."),
    ("double-hyphen", "Ashford level it -- at last.", "Ashford level it, at last."),
    (
        "not-just-but",
        "Not just fast but direct.",
        "Not just fast. The other side is direct.",
    ),
    ("showcase", "Ashford showcase the press.", "Ashford show the press."),
    ("testament", "A testament to the press.", "The press is tested."),
    ("delve", "Let us delve into it.", "The keeper dealt with it."),
    ("seamless", "A seamless move.", "A move without a break."),
    ("leverage", "They leverage width.", "They use width."),
    ("unlock", "Rivermouth unlock the defence.", "Rivermouth open the defence."),
    ("game-changer", "A game changer.", "A game, changed."),
    ("dramatic-turn", "A dramatic turn of events.", "A turn in the half."),
    ("worth-noting", "It's worth noting the corner.", "Note the corner."),
    ("masterclass", "A masterclass in pressing.", "A class of pressing."),
    ("tapestry", "A tapestry of passes.", "A string of passes."),
    ("pivotal", "A pivotal tackle.", "A tackle on the pivot."),
    ("in-todays", "In today's game.", "Today the game is level."),
    ("emoji", "Ashford score ⚽", "Ashford score ′"),
    ("exclamation", "Ashford score!", "Ashford score."),
    ("hedging", "Ashford seem to tire.", "Ashford seem tired."),
    ("long-sentence", " ".join(["word"] * 31) + ".", " ".join(["word"] * 30) + "."),
    ("player-id", "away-10 scores.", "The Ashford No. 10 scores."),
    ("event-id", "Since ev-001484 they sit deep.", "Since the red card they sit deep."),
    ("snake-case-token", "A second_yellow is shown.", "A second yellow is shown."),
    ("since-the-event", "Deeper since the event.", "Deeper since the red card."),
    ("freeze-frame", "The freeze frame shows one.", "One defender is in the way."),
    ("zone-players", "Two zone defenders wait.", "Two defenders wait."),
    ("clock-time", "Shot at 97:22.", "Shot at 90+7′."),
    ("zero-count", "The move has 0 passes.", "The move has no passes."),
    (
        "many-numbers",
        "A 4 second move, 7 m out, worth 0.30 xG at 9′.",
        "A 4 second move, 7 m out, at 9′.",
    ),
    (
        "evaluative-adjective",
        "Rivermouth score a brilliant goal.",
        "Rivermouth score from 7 m out.",
    ),
    (
        "shielding",
        "Ashford Vale are shielding their goal.",
        "Ashford Vale have two defenders near their goal.",
    ),
]


@pytest.mark.parametrize(("rule_id", "bad", "ok"), CASES)
def test_rule_fires_and_near_miss_is_quiet(rule_id: str, bad: str, ok: str) -> None:
    assert rule_id in ids(bad, "narration")
    assert rule_id not in ids(ok, "narration")


def test_every_rule_is_covered() -> None:
    covered = {c[0] for c in CASES} | {
        "ui-ai",
        "ui-agent",
        "ui-generated",
        "ui-sparkle",
    }
    assert {r.id for r in RULES} == covered


def test_ui_rules_skip_narration() -> None:
    assert not ids("The AI agent generated this ✨", "narration") & {
        "ui-ai",
        "ui-agent",
        "ui-generated",
        "ui-sparkle",
    }
    assert {"ui-ai", "ui-agent", "ui-generated", "ui-sparkle"} <= ids(
        "The AI agent generated this ✨", "ui"
    )
    assert "ui-ai" not in ids("Said the aide", "ui")


def test_narration_rules_skip_ui() -> None:
    assert "exclamation" in ids("Goal!", "narration")
    assert "exclamation" not in ids("Goal!", "ui")
    assert "long-sentence" not in ids(" ".join(["word"] * 40) + ".", "ui")


def test_numbers_in() -> None:
    assert numbers_in("6 times, 8 m out, 41′, xG 0.31") == ["6", "8 m", "41′", "0.31"]
    assert numbers_in("no digits here") == []


def load_examples() -> list[dict[str, Any]]:
    return cast_list(
        yaml.safe_load((ROOT / "voice" / "examples.yaml").read_text(encoding="utf-8"))
    )


def cast_list(raw: Any) -> list[dict[str, Any]]:
    assert isinstance(raw, list)
    return raw


EXAMPLES = load_examples()
REAL = [e for e in EXAMPLES if not e.get("format_only")]


@pytest.mark.parametrize("ex", REAL, ids=[e["id"] for e in REAL])
def test_example_lints_clean(ex: dict[str, Any]) -> None:
    errors = [v for v in lint(ex["line"], "narration", RULES) if v.severity == "error"]
    assert not errors


def check_numbers_from_facts(ex: dict[str, Any]) -> None:
    allowed = {n for f in ex["facts"] for n in numbers_in(f["display"])}
    missing = [n for n in numbers_in(ex["line"]) if n not in allowed]
    assert not missing, missing


@pytest.mark.parametrize("ex", REAL, ids=[e["id"] for e in REAL])
def test_example_numbers_come_from_facts(ex: dict[str, Any]) -> None:
    check_numbers_from_facts(ex)


@pytest.mark.xfail(
    strict=True, reason="ex-00 is deliberately flawed: 41 metres has no fact"
)
def test_format_example_numbers_fail() -> None:
    ex = next(e for e in EXAMPLES if e["id"] == "ex-00")
    check_numbers_from_facts(ex)


@pytest.mark.parametrize("ex", EXAMPLES, ids=[e["id"] for e in EXAMPLES])
def test_example_shape(ex: dict[str, Any]) -> None:
    beat = json.loads(
        (ROOT / "schemas" / "beat.schema.json").read_text(encoding="utf-8")
    )
    assert ex["beat_kind"] in beat["properties"]["kind"]["enum"]
    assert ex["mode"] in {"fan", "analyst", "producer"}
    assert len(ex["line"].split()) <= 30
    assert ex["source"] in {"original", "adapted"}
    if ex["source"] == "adapted" and "source_ref" in ex:
        assert len(ex["source_ref"]) == 3 and ex["source_ref"][0] == "S"
        assert ex["source_ref"][1:].isdigit()
    if ex["amended_from"] is not None or ex["reason"] is not None:
        assert ex["amended_from"] and ex["reason"]


def test_amended_examples_have_both_fields() -> None:
    for ex in EXAMPLES:
        assert (ex["amended_from"] is None) == (ex["reason"] is None), ex["id"]


@pytest.mark.parametrize(
    "path", sorted((ROOT / "apps/web/src/copy").glob("*.json")), ids=str
)
def test_copy_files_lint_clean(path: Path) -> None:
    def walk(node: Any) -> list[str]:
        if isinstance(node, str):
            return [node]
        children = node.values() if isinstance(node, dict) else node
        return [s for c in children for s in walk(c)]

    data = json.loads(path.read_text(encoding="utf-8"))
    for s in walk(data):
        assert not [v for v in lint(s, "ui", RULES) if v.severity == "error"], s
