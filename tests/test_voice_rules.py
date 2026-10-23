"""The narration rules added in prompt 08.1."""

from pathlib import Path

import pytest
import yaml
from intel.voice_lint import lint

EXAMPLES = yaml.safe_load(
    (Path(__file__).resolve().parents[1] / "voice" / "examples.yaml").read_text("utf-8")
)

# Bad lines from the first end-to-end run, and the rule each must trip.
BAD = [
    ("Ashford Vale's away-10 fires a 0.30 xG shot.", "player-id", "error"),
    ("Away player gets a second_yellow and is sent off.", "snake-case-token", "error"),
    ("Ashford Vale have taken more of the ball since ev-001484.", "event-id", "error"),
    ("Ashford Vale have more of the ball since the event.", "since-the-event", "error"),
    ("The freeze frame shows one defender.", "freeze-frame", "error"),
    ("There are 3 zone defenders in the box.", "zone-players", "error"),
    ("They shoot 3 seconds after the ball was won at 97:22.", "clock-time", "error"),
    ("The move has 0 passes.", "zero-count", "warn"),
    ("A 4 second move, 7 m out, worth 0.30 xG at 9′.", "many-numbers", "warn"),
]
# Lines in voice/examples.yaml that trip a new warning, which the examples themselves teach: ex-01
# has four numbers and ex-02 a zero count. No example trips an error rule. The Narrator's few-shot
# loader leaves the warned lines out, so the model is never shown a line that breaks a rule.
KNOWN = {
    "ex-01": {"many-numbers"},
    "ex-02": {"zero-count"},
}


@pytest.mark.parametrize(("text", "rule", "severity"), BAD)
def test_new_rules_fire_on_the_bad_lines(text: str, rule: str, severity: str) -> None:
    hits = {v.rule_id: v.severity for v in lint(text, "narration")}
    assert hits.get(rule) == severity, hits


def test_new_rules_are_quiet_on_the_example_lines() -> None:
    for e in EXAMPLES:
        fired = {v.rule_id for v in lint(e["line"], "narration")}
        if e["id"] == "ex-00":
            continue  # deliberately flawed, format only
        assert fired == KNOWN.get(e["id"], set()), (e["id"], fired)


def test_the_new_rules_do_not_touch_ui_copy() -> None:
    assert lint("away-10 second_yellow 97:22", "ui") == []
