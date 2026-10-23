"""The Producer: which beats get narrated, and in what order.

The hard rules are code. The model only judges inside them: salience, variety, and whether a beat
adds anything new given the beats already narrated.

- Goals, red cards and follow-up momentum swings are always narrated.
- At most NARRATION_BUDGET beats a match are chosen by judgement. The always-narrated beats are not
  held back by it, so a match with more than that many of them narrates them all.
- No two narrated beats of one kind within SAME_KIND_GAP_S of each other, except goals.

`rank` runs 1..n over the narrated beats in the order they were decided, with no gaps.
"""

import threading
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from intel.voice_lint import lint
from pydantic import BaseModel, Field

from .llm_client import ChatClient, LlmError
from .structured import StructuredOutputError, complete_structured

NARRATION_BUDGET = 12
SAME_KIND_GAP_S = 180.0  # 3 match minutes
FALLBACK_SALIENCE = (
    0.6  # with no model answer, narrate a discretionary beat at or above this
)
PROMPT_PATH = Path(__file__).parent / "prompts" / "producer.v1.md"

GOAL_KINDS = frozenset(
    {"counter_goal", "set_piece_goal", "high_turnover_goal", "open_play_goal"}
)
ALWAYS_KINDS = GOAL_KINDS | {"card", "momentum_swing"}
KIND_WORDS = {
    "counter_goal": "counter-attack goal",
    "set_piece_goal": "set-piece goal",
    "high_turnover_goal": "goal from a high turnover",
    "open_play_goal": "goal from open play",
    "high_turnover_chance": "chance from a high turnover",
    "big_chance": "big chance",
    "territorial_spell": "spell of territory",
    "momentum_swing": "shift after a goal or red card",
    "card": "red card",
    "substitution": "substitution",
}
FORCED_PRIORITY = {"card": 5, "momentum_swing": 4}


class ProducerAnswer(BaseModel):
    narrate: bool
    priority: int = Field(ge=1, le=5)
    note: str = Field(max_length=160)


@dataclass(frozen=True)
class Decision:
    beat_id: str
    kind: str
    narrate: bool
    priority: int
    note: str
    rank: int | None = None
    forced: bool = False
    reason: str = "model"  # forced, budget, spacing, model or fallback

    def as_log(self, t: float) -> dict[str, Any]:
        return {
            "beat_id": self.beat_id,
            "t": t,
            "kind": self.kind,
            "narrate": self.narrate,
            "priority": self.priority,
            "rank": self.rank,
            "decided_by": self.reason,
            "note": self.note,
        }


def _minute(beat: dict[str, Any]) -> str:
    return str(beat["label"])


class Producer:
    """Decides beats one at a time, in the order they are found. Thread-safe."""

    def __init__(
        self, client: ChatClient | None, *, budget: int = NARRATION_BUDGET
    ) -> None:
        self._client = client
        self._budget = budget
        self._lock = threading.Lock()
        self._narrated: list[tuple[str, str, float]] = []  # kind, label, t
        self._judged = 0  # narrated by judgement, counted against the budget
        self.log: list[dict[str, Any]] = []
        self.tokens = 0
        self.calls = 0

    def decide(self, beat: dict[str, Any], teams: dict[str, str]) -> Decision:
        with self._lock:
            decision = self._decide(beat, teams)
            if decision.narrate:
                self._narrated.append((decision.kind, _minute(beat), _t(beat)))
                decision = replace(decision, rank=len(self._narrated))
            self.log.append(decision.as_log(_t(beat)))
            return decision

    def note_audit(self, line: str) -> None:
        """A plain line in the log, for an auditor disagreement."""
        with self._lock:
            self.log.append({"audit": line})

    def _decide(self, beat: dict[str, Any], teams: dict[str, str]) -> Decision:
        kind, bid = str(beat["kind"]), str(beat["id"])
        word = KIND_WORDS.get(kind, kind.replace("_", " "))
        label = _minute(beat)
        if kind in ALWAYS_KINDS:
            return Decision(
                bid,
                kind,
                True,
                5 if kind in GOAL_KINDS else FORCED_PRIORITY[kind],
                f"The {word} at {label} is always on the feed.",
                forced=True,
                reason="forced",
            )
        if self._judged >= self._budget:
            return Decision(
                bid,
                kind,
                False,
                1,
                f"The {word} at {label} is left off; the feed is full.",
                reason="budget",
            )
        last = next(
            (t for k, _, t in reversed(self._narrated) if k == kind),
            None,
        )
        if last is not None and _t(beat) - last < SAME_KIND_GAP_S:
            return Decision(
                bid,
                kind,
                False,
                1,
                f"The {word} at {label} is left off; one ran just before it.",
                reason="spacing",
            )
        answer, reason = self._ask(beat, teams, word, label)
        if answer.narrate:
            self._judged += 1
        return Decision(
            bid, kind, answer.narrate, answer.priority, answer.note, reason=reason
        )

    def _ask(
        self, beat: dict[str, Any], teams: dict[str, str], word: str, label: str
    ) -> tuple[ProducerAnswer, str]:
        salience = float(beat["salience"])
        fallback = ProducerAnswer(
            narrate=salience >= FALLBACK_SALIENCE,
            priority=max(1, min(5, round(salience * 5))),
            note=f"The {word} at {label} is "
            + ("on the feed." if salience >= FALLBACK_SALIENCE else "left off.")
            + " The producer is unavailable.",
        )
        if self._client is None:
            return fallback, "fallback"
        side = f" for {teams[beat['side']]}" if beat.get("side") else ""
        narrated = (
            "; ".join(
                f"{KIND_WORDS.get(k, k)} at {lbl}" for k, lbl, _ in self._narrated
            )
            or "nothing yet"
        )
        values = {
            "home": teams["home"],
            "away": teams["away"],
            "kind": word,
            "label": label,
            "side": side,
            "salience": f"{salience:.2f}",
            "count": str(len(self._narrated)),
            "budget": str(self._budget),
            "narrated": narrated,
        }
        prompt = PROMPT_PATH.read_text("utf-8")
        for key, value in values.items():
            prompt = prompt.replace("{{" + key + "}}", value)
        try:
            out = complete_structured(
                self._client, ProducerAnswer, prompt, max_tokens=300
            )
        except (LlmError, StructuredOutputError):
            return fallback, "fallback"
        self.calls += 1
        self.tokens += out.input_tokens + out.output_tokens
        answer = out.value
        broken = [v for v in lint(answer.note, "narration") if v.severity == "error"]
        if broken:  # the log follows the voice rules; code decides, not the model
            answer = answer.model_copy(
                update={
                    "note": f"The {word} at {label} is "
                    + ("on the feed." if answer.narrate else "left off.")
                }
            )
        return answer, "model"


def _t(beat: dict[str, Any]) -> float:
    return float(beat["t_from"])
