"""Turn the auditor's disagreements into eval cases.

    uv run python -m evals.from_audit data/archive/m-red-card-flip-3/audit.json
    uv run python -m evals.from_audit http://localhost:8000/matches/m-red-card-flip-3/audit

Every auditor disagreement becomes an eval case: paste the YAML this prints at the end of the bad
claims in evals/adversarial/claims.yaml (before the good ones), check that the text and facts say what
went wrong, then update the totals in evals/pick.py and tests/test_evals.py and re-run `make bakeoff`.
The match is taken from the audit's match id (`m-<story>-<seed>`); pass --story and --seed for
anything else, such as a custom brief.
"""

import argparse
import json
import re
import urllib.request
from pathlib import Path
from typing import Any

CLAIMS_PATH = Path(__file__).resolve().parent / "adversarial" / "claims.yaml"
KIND_OF_PROBLEM = {
    "overclaim": "overclaim",
    "motive": "motive",
    "unsupported_cause": "invented_cause",
    "wrong_entity": "wrong_entity",
    "wrong_time": "wrong_minute",
    "outside_knowledge": "outside_knowledge",
}
MATCH_ID = re.compile(r"^m-(?P<story>[a-z-]+?)-(?P<seed>\d+)$")


def read_audit(source: str) -> dict[str, Any]:
    if source.startswith(("http://", "https://")):
        with urllib.request.urlopen(source, timeout=30) as response:
            audit: dict[str, Any] = json.load(response)
    else:
        audit = json.loads(Path(source).read_text("utf-8"))
    return audit


def next_number(claims_text: str) -> int:
    numbers = [
        int(n) for n in re.findall(r"^- id: adv-(\d+)$", claims_text, re.MULTILINE)
    ]
    return max(numbers, default=0) + 1


def match_of(
    audit: dict[str, Any], story: str | None, seed: int | None
) -> tuple[str, int]:
    found = MATCH_ID.match(str(audit["match_id"]))
    if story is None or seed is None:
        if found is None:
            raise SystemExit(
                f"cannot read a story and seed from {audit['match_id']!r}; pass --story and --seed"
            )
        story = story or found["story"].replace("-", "_")
        seed = seed if seed is not None else int(found["seed"])
    return story, seed


def entries(
    audit: dict[str, Any],
    start: int,
    story: str | None = None,
    seed: int | None = None,
) -> str:
    """YAML eval entries, one per disagreement, numbered from adv-{start}."""
    story, seed = match_of(audit, story, seed)
    out: list[str] = []
    for i, d in enumerate(audit["disagreements"]):
        problem = d["auditor"]["problem"] or "overclaim"
        reason = (d["auditor"]["reason"] or "").replace("\n", " ")
        fact_ids = d["fact_ids"]
        out.append(
            f"# {d['claim_id']} ({d['verdict']}); {d['auditor']['deployment']} ({problem}): {reason}\n"
            f"- id: adv-{start + i}\n"
            f"  kind: {KIND_OF_PROBLEM.get(problem, 'overclaim')}\n"
            f"  match: {{ story: {story}, seed: {seed} }}\n"
            f"  beat_id: {d['beat_id']}\n"
            f"  text: {json.dumps(d['text'], ensure_ascii=False)}\n"
            f"  fact_ids: [{', '.join(fact_ids)}]\n"
            f"  expected: rephrased\n"
        )
    return "".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "audit", help="path to audit.json, or the /matches/{id}/audit URL"
    )
    parser.add_argument("--story")
    parser.add_argument("--seed", type=int)
    args = parser.parse_args()
    audit = read_audit(args.audit)
    if not audit["disagreements"]:
        print("# no disagreements")
        return
    start = next_number(CLAIMS_PATH.read_text("utf-8"))
    print(entries(audit, start, args.story, args.seed), end="")


if __name__ == "__main__":
    main()
