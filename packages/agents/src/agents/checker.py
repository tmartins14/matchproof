"""The Checker: reconcile numbers, run the voice lint, then ask an LLM judge about the wording.

Code runs before judgement (seam rule): a claim that fails reconciliation or the lint never reaches
the judge. A failed claim goes back to the Narrator once with the reasons; if the retry passes the
claim is `rephrased`, if not it is `blocked`. A judge that cannot answer in time leaves the claim
`delayed`.
"""

import contextvars
import re
from collections.abc import Callable, Collection, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from contracts.models import Claim, Fact
from intel.labels import say
from intel.voice_lint import Rule, lint, load_rules
from opentelemetry import trace
from pydantic import BaseModel

from .llm_client import ChatClient, LlmError, load_models
from .narrator import DraftClaim, Revision
from .reconcile import NumberMatch, reconcile
from .structured import StructuredOutputError, complete_structured

JUDGE_TIMEOUT_S = 6.0
JUDGE_MAX_TOKENS = 800
MAX_WORKERS = 4  # claims of one beat checked at the same time
PROMPTS_DIR = Path(__file__).parent / "prompts"
MAX_REASON_CHARS = 400
_tracer = trace.get_tracer(__name__)

Problem = Literal[
    "overclaim",
    "motive",
    "unsupported_cause",
    "wrong_entity",
    "wrong_time",
    "outside_knowledge",
]


class JudgeAnswer(BaseModel):
    supported: bool
    problem: Problem | None = None
    reason: str = ""


@dataclass
class ClaimCheck:
    """The outcome of checking one draft once."""

    text: str
    fact_ids: list[str]
    numbers: list[NumberMatch] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    reconciled: bool = False
    lint_ok: bool = False
    judge_supported: bool | None = (
        None  # None: the judge was not asked or did not answer
    )
    judge_problem: str | None = None
    judge_reason: str = ""  # what the judge said, whether or not it passed the claim
    judged: bool = False
    delayed: bool = False
    model: str | None = None
    latency_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def passed(self) -> bool:
        return not self.reasons and not self.delayed

    @property
    def caught_by_code(self) -> bool:
        return not self.reconciled or not self.lint_ok


@dataclass
class CheckedClaim:
    claim: Claim
    first: ClaimCheck
    final: ClaimCheck


def judge_prompt_path(name: str | None = None) -> Path:
    """The judge prompt file: `name`, else `judge_prompt` in config/models.yaml."""
    return PROMPTS_DIR / (name or str(load_models()["judge_prompt"]))


def render_judge_prompt(
    check_text: str,
    facts: list[Fact],
    teams: Mapping[str, str],
    beat_kind: str,
    beat_label: str,
    labels: Mapping[str, str] | None = None,
    prompt_file: str | None = None,
) -> str:
    lines = []
    for f in facts:
        side = teams[f.scope.side.value] if f.scope and f.scope.side else "n/a"
        unit = f" {f.unit.value}" if f.unit else ""
        what = (labels or {}).get(f.id.root, f.name)
        lines.append(
            f"- {f.id.root}: {what} = {f.value}{unit}; may be written as "
            f"{' | '.join(say(f.value, f.display.en, teams))}; side {side}"
        )
    values = {
        "home": teams["home"],
        "away": teams["away"],
        "beat_kind": beat_kind,
        "beat_label": beat_label,
        "claim": check_text,
        "facts": "\n".join(lines),
    }
    prompt = judge_prompt_path(prompt_file).read_text("utf-8")
    for key, value in values.items():
        prompt = prompt.replace("{{" + key + "}}", value)
    return prompt


class Checker:
    def __init__(
        self,
        judge: ChatClient,
        *,
        rules: list[Rule] | None = None,
        timeout_s: float = JUDGE_TIMEOUT_S,
        max_workers: int = MAX_WORKERS,
        prompt_file: str | None = None,
    ) -> None:
        self._workers = max_workers
        self._prompt_file = prompt_file
        self._judge = judge
        self._rules = rules if rules is not None else load_rules()
        self._timeout_s = timeout_s

    def check_one(
        self,
        draft: DraftClaim,
        bundle: Mapping[str, Fact],
        *,
        teams: Mapping[str, str],
        beat_kind: str,
        beat_label: str,
        labels: Mapping[str, str] | None = None,
        names: Collection[str] = (),
    ) -> ClaimCheck:
        """Reconcile, lint, then judge. The judge is asked only if the code checks pass."""
        with _tracer.start_as_current_span("reconcile") as span:
            rec = reconcile(draft.text, draft.fact_ids, bundle, names)
            span.set_attribute("matchproof.ok", rec.ok)
        result = ClaimCheck(draft.text, list(draft.fact_ids), rec.numbers)
        result.reconciled = rec.ok
        result.reasons.extend(rec.reasons)
        with _tracer.start_as_current_span("lint") as span:
            violations = [
                v
                for v in lint(draft.text, "narration", self._rules)
                if v.severity == "error"
            ]
            span.set_attribute("matchproof.ok", not violations)
        result.lint_ok = not violations
        rule_why = {r.id: r.why for r in self._rules}
        for v in violations:
            result.reasons.append(
                f'Voice rule {v.rule_id} broken by "{v.excerpt}": {rule_why.get(v.rule_id, "")}'.strip()
            )
        if result.reasons:
            return result
        prompt = render_judge_prompt(
            draft.text,
            [bundle[f] for f in draft.fact_ids],
            teams,
            beat_kind,
            beat_label,
            labels,
            self._prompt_file,
        )
        result.judged = True
        try:
            with _tracer.start_as_current_span(
                "judge", attributes={"gen_ai.request.model": self._judge.deployment}
            ) as judge_span:
                reply = complete_structured(
                    self._judge,
                    JudgeAnswer,
                    prompt,
                    max_tokens=JUDGE_MAX_TOKENS,
                    timeout_s=self._timeout_s,
                )
                judge_span.set_attribute(
                    "gen_ai.usage.input_tokens", reply.input_tokens
                )
                judge_span.set_attribute(
                    "gen_ai.usage.output_tokens", reply.output_tokens
                )
                judge_span.set_attribute(
                    "matchproof.judge.supported", reply.value.supported
                )
        except (LlmError, StructuredOutputError) as exc:
            result.delayed = True
            result.model = self._judge.deployment
            result.reasons.append(f"Judge did not answer: {type(exc).__name__}.")
            return result
        answer = reply.value
        result.model = reply.model
        result.latency_ms = reply.latency_ms
        result.input_tokens = reply.input_tokens
        result.output_tokens = reply.output_tokens
        result.judge_supported = answer.supported
        result.judge_problem = answer.problem
        result.judge_reason = answer.reason
        if not answer.supported:
            problem = answer.problem or "unsupported"
            result.reasons.append(f"Judge ({problem}): {answer.reason}".strip())
        return result

    def check_all(
        self,
        drafts: list[DraftClaim],
        bundle: Mapping[str, Fact],
        *,
        teams: Mapping[str, str],
        beat_kind: str,
        beat_label: str,
        labels: Mapping[str, str] | None = None,
        names: Collection[str] = (),
    ) -> list[ClaimCheck]:
        """Check every draft of a beat, a few at a time."""

        def check(d: DraftClaim) -> ClaimCheck:
            return self.check_one(
                d,
                bundle,
                teams=teams,
                beat_kind=beat_kind,
                beat_label=beat_label,
                labels=labels,
                names=names,
            )

        # Each task runs in its own copy of the caller's context, taken here: a pool thread's own
        # context is empty, so its spans would start new traces instead of nesting under `check`.
        contexts = [contextvars.copy_context() for _ in drafts]
        with ThreadPoolExecutor(max_workers=self._workers) as pool:
            return list(
                pool.map(lambda cd: cd[0].run(check, cd[1]), zip(contexts, drafts))
            )

    @staticmethod
    def plan_retry(
        drafts: list[DraftClaim], first: list[ClaimCheck]
    ) -> tuple[list[int], Revision | None]:
        """The drafts that failed their first check and what to tell the Narrator about them."""
        failed = [i for i, c in enumerate(first) if not c.passed and not c.delayed]
        if not failed:
            return failed, None
        return failed, Revision(
            draft=[drafts[i] for i in failed],
            reasons=[
                f"Claim {n}: {r}"
                for n, i in enumerate(failed, 1)
                for r in first[i].reasons
            ],
            kept=[drafts[i].text for i, c in enumerate(first) if c.passed],
        )

    @staticmethod
    def accept_revisions(
        failed: list[int], revision: Revision, new: list[DraftClaim]
    ) -> dict[int, DraftClaim]:
        """Pair the Narrator's new drafts with the claims they replace; a repeat of an accepted claim
        is no fix."""
        kept = {t.strip().lower() for t in revision.kept}
        return {
            i: n
            for i, n in zip(failed, new, strict=False)
            if n.text.strip().lower() not in kept
        }

    def settle(
        self,
        drafts: list[DraftClaim],
        first: list[ClaimCheck],
        failed: list[int],
        redone: Mapping[int, ClaimCheck],
        *,
        beat_id: str,
        lang: str,
    ) -> list[CheckedClaim]:
        """The checked claims, from the first checks and the re-checks of the revised drafts."""
        stem = re.sub(r"^bt-", "", beat_id)
        out: list[CheckedClaim] = []
        for i, (draft, c1) in enumerate(zip(drafts, first, strict=True)):
            claim_id = f"cl-{stem}-{i + 1:02d}"
            retries = 1 if i in failed else 0
            out.append(
                self._finish(
                    claim_id, beat_id, lang, draft, c1, redone.get(i, c1), retries
                )
            )
        return out

    def check_beat(
        self,
        drafts: list[DraftClaim],
        bundle: Mapping[str, Fact],
        *,
        beat_id: str,
        lang: str,
        teams: Mapping[str, str],
        beat_kind: str,
        beat_label: str,
        labels: Mapping[str, str] | None = None,
        names: Collection[str] = (),
        renarrate: Callable[[Revision], list[DraftClaim]],
    ) -> list[CheckedClaim]:
        """Check a beat's drafts, send the failures back to `renarrate` once, and re-check."""
        context = {
            "teams": teams,
            "beat_kind": beat_kind,
            "beat_label": beat_label,
            "labels": labels,
            "names": names,
        }
        first = self.check_all(drafts, bundle, **context)  # type: ignore[arg-type]
        failed, revision = self.plan_retry(drafts, first)
        revised: dict[int, DraftClaim] = {}
        if revision is not None:
            revised = self.accept_revisions(failed, revision, renarrate(revision))
        again = self.check_all(list(revised.values()), bundle, **context)  # type: ignore[arg-type]
        redone = dict(zip(revised, again, strict=True))
        return self.settle(drafts, first, failed, redone, beat_id=beat_id, lang=lang)

    @staticmethod
    def _finish(
        claim_id: str,
        beat_id: str,
        lang: str,
        draft: DraftClaim,
        first: ClaimCheck,
        final: ClaimCheck,
        retries: int,
    ) -> CheckedClaim:
        if final.delayed:
            verdict = "delayed"
        elif final.passed:
            verdict = "verified" if retries == 0 else "rephrased"
        else:
            verdict = "blocked"
        reason = "; ".join(first.reasons if retries else final.reasons)[
            :MAX_REASON_CHARS
        ]
        if verdict == "blocked":
            reason = "; ".join(final.reasons)[:MAX_REASON_CHARS]
        data: dict[str, object] = {
            "id": claim_id,
            "beat_id": beat_id,
            "lang": lang,
            "text": final.text,
            "fact_ids": final.fact_ids,
            "numbers": [
                {"as_written": n.as_written, "fact_id": n.fact_id}
                for n in final.numbers
            ],
            "verdict": verdict,
            "checker": {
                "reconciled": final.reconciled,
                **(
                    {"judge_supported": final.judge_supported}
                    if final.judge_supported is not None
                    else {}
                ),
                "retries": retries,
                "model": final.model or first.model or "code",
                "latency_ms": final.latency_ms + (first.latency_ms if retries else 0),
            },
        }
        if verdict in ("rephrased", "blocked", "delayed") and reason:
            data["reason"] = reason
        if verdict in ("rephrased", "blocked") or (verdict == "delayed" and retries):
            data["draft_text"] = draft.text
        return CheckedClaim(Claim.model_validate(data), first, final)
