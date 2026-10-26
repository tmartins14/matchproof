import Link from "next/link";
import { copy, fill } from "@/desk/copy";
import { candidateById, rankOf, scoredClaim, summaryOf, web } from "@/trials/data";
import { amendedParts, reasonLine, seconds, verdictKey } from "@/trials/format";
import { VerdictStamp } from "../desk/VerdictStamp";

function Prose({ fixture, beat, candidate }: { fixture: string; beat: string; candidate: string }) {
  const t = copy.en.trials.compare;
  const row = scoredClaim(candidate, fixture, beat);
  if (!row) return <p className="tr-claim tr-dim">{t.noRow}</p>;
  if (row.lost !== null) {
    const why = copy.en.trials.lost[row.lost];
    return (
      <>
        <p className="tr-claim">{fill(t.noClaim, { reason: why })}</p>
        {row.lost === "rejected" && row.draft_text ? (
          <p className="tr-draft">
            <span className="tr-hd">{t.draftLabel}</span> {row.draft_text} <span className="tr-note">({t.badCitation})</span>
          </p>
        ) : null}
        {row.lost === "no_answer" ? null : <p className="tr-reason">{row.reasons.join(" ")}</p>}
      </>
    );
  }
  if (row.verdict === "AMENDED") {
    const parts = amendedParts(row);
    if (parts) {
      return (
        <>
          <p className="tr-claim">
            {parts.before}
            <del className="tr-bad">{parts.failed}</del>
            <ins className="tr-fix">{parts.corrected}</ins>
            {parts.after}
          </p>
          <p className="tr-reason">{reasonLine(row)}</p>
        </>
      );
    }
  }
  return (
    <>
      <p className="tr-claim">{row.text}</p>
      {row.verdict === "OVERTURNED" && row.reasons.length > 0 ? <p className="tr-reason">{reasonLine(row)}</p> : null}
    </>
  );
}

/** One candidate's scored claim on this beat. Prose is not ranked; only what failed is marked. */
export function NarratorCard({ candidate, fixture, beat, focused }: { candidate: string; fixture: string; beat: string; focused: boolean }) {
  const t = copy.en.trials.compare;
  const c = copy.en;
  const row = scoredClaim(candidate, fixture, beat);
  const rank = rankOf(candidate);
  const summary = summaryOf(candidate);
  const cleared = summary?.cleared === true && rank !== undefined;
  const verdict = row ? row.verdict : "HELD";
  const tone = row ? verdictKey(row.verdict) : "delayed";
  return (
    <article id={`card-${candidate}`} className={`tr-card tr-ncard tr-ncard--${tone}${focused ? " tr-ncard--focus" : ""}`} aria-label={candidate}>
      <header className="tr-ncard-head">
        <div>
          <div className="tr-hd">{fill(t.narrator, { rank: rank === undefined ? t.notRanked : (t.ordinal[rank - 1] ?? String(rank)) })}</div>
          <div className="tr-ncard-name">{candidateById(candidate)?.id ?? candidate}</div>
        </div>
        <VerdictStamp verdict={verdictKey(verdict)} copy={c} />
      </header>
      <Prose fixture={fixture} beat={beat} candidate={candidate} />
      {row && row.lost === null ? (
        <div className="tr-mono">
          {fill(t.checker, {
            checker: row.checker,
            auditor: row.auditor,
            s: row.narrator_ms === null ? "n/a" : seconds(row.narrator_ms),
          })}
          {row.referee_split ? ` · ${t.split}` : ""}
        </div>
      ) : null}
      {rank !== undefined && !cleared ? <span className="tr-tag tr-tag--out">{copy.en.trials.table.notCleared}</span> : null}
      {cleared ? (
        <Link href={`/desk?narrator=${candidate}&fixture=${fixture}`} className="tr-btn tr-btn--sm">
          {copy.en.trials.table.useOnDesk}
        </Link>
      ) : null}
    </article>
  );
}

export const narratorCount = (): number => web.order.length;
