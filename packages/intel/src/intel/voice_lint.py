"""Deterministic voice lint for product text (narration and UI copy).

Rules live in voice/banned.yaml. No LLM calls, no network.
"""

import json
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from contracts.paths import runtime_root

Scope = Literal["narration", "ui"]
Severity = Literal["error", "warn"]

DEFAULT_RULES_PATH = runtime_root() / "voice" / "banned.yaml"

_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*(?:[′']|%| ?(?:km|m)\b)?")


@dataclass(frozen=True)
class Rule:
    id: str
    pattern: re.Pattern[str]
    severity: Severity
    applies_to: tuple[Scope, ...]
    why: str


@dataclass(frozen=True)
class Violation:
    rule_id: str
    severity: Severity
    start: int
    end: int
    excerpt: str


def load_rules(path: Path | None = None) -> list[Rule]:
    raw = yaml.safe_load((path or DEFAULT_RULES_PATH).read_text(encoding="utf-8"))
    return [
        Rule(
            id=r["id"],
            pattern=re.compile(r["pattern"], re.IGNORECASE),
            severity=r["severity"],
            applies_to=tuple(r["applies_to"]),
            why=r["why"],
        )
        for r in raw
    ]


def lint(
    text: str, applies_to: Scope, rules: list[Rule] | None = None
) -> list[Violation]:
    active = rules if rules is not None else load_rules()
    found = [
        Violation(r.id, r.severity, m.start(), m.end(), m.group(0))
        for r in active
        if applies_to in r.applies_to
        for m in r.pattern.finditer(text)
    ]
    return sorted(found, key=lambda v: (v.start, v.rule_id))


def numbers_in(text: str) -> list[str]:
    """Numeric tokens in text, e.g. "6", "8 m", "41′", "0.31". Number words are out of scope."""
    return [m.group(0) for m in _NUMBER_RE.finditer(text)]


def _strings(node: Any, path: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from _strings(v, f"{path}.{k}" if path else str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _strings(v, f"{path}[{i}]")


def main(argv: list[str]) -> int:
    rules = load_rules()
    errors = 0
    for name in argv:
        data = json.loads(Path(name).read_text(encoding="utf-8"))
        for key, value in _strings(data):
            for v in lint(value, "ui", rules):
                errors += v.severity == "error"
                print(f"{name}: {key}: {v.severity} {v.rule_id}: {v.excerpt!r}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
