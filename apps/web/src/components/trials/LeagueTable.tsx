import Link from "next/link";
import { copy, fill } from "@/desk/copy";
import { candidateById, clockOfWorst, failTopOf, firstTrapBeat, rankOf, summaryOf, tableOrder, trapRecordOf, web, worstOf, type SummaryRow } from "@/trials/data";
import { compactTokens, fixtureNumber, seconds } from "@/trials/format";
import { FailBar } from "./FailBar";

function compareHref(id: string): string {
  const worst = worstOf(id);
  const fixture = worst?.fixture ?? "fx-01";
  const beat = worst?.beat ?? firstTrapBeat(fixture) ?? "";
  return `/compare/${fixture}/${beat}?focus=${id}`;
}

function Row({ row, leader }: { row: SummaryRow; leader: boolean }) {
  const t = copy.en.trials;
  const id = row.candidate;
  const rank = rankOf(id);
  const worst = worstOf(id);
  const self = candidateById(id)?.self_audited === true;
  const cleared = row.cleared && rank !== undefined;
  // An unmeasured narrator that audits itself and was the cleanest when it did answer.
  const auditorNote = self && rank === undefined && row.held > 0 && row.clean_pct !== null && row.clean_pct >= Math.max(...web.results.summary.map((r) => r.clean_pct ?? 0));
  const state = !cleared && rank !== undefined ? " tr-row--out" : "";
  const record = trapRecordOf(id);
  const trapTotal = record ? record.STANDS + record.AMENDED + record.OVERTURNED + record.HELD : 0;
  const top = failTopOf(id);
  const price = typeof row.usd_per_match === "string" ? t.table.priceNotSet : `$${row.usd_per_match.toFixed(4)}`;
  return (
    <div role="row" className={`tr-row${leader ? " tr-row--lead" : ""}${state}${rank === undefined ? " tr-row--unmeasured" : ""}`}>
      <div role="cell" className="tr-num">
        {rank ?? ""}
      </div>
      <div role="cell" className="tr-who">
        <Link href={compareHref(id)} className="tr-who-link">
          {id}
        </Link>
        <div className="tr-sub">
          {t.table.provider} ·{" "}
          {worst
            ? fill(t.table.worst, { note: worst.note, fixture: fixtureNumber(worst.fixture), clock: clockOfWorst(worst) })
            : auditorNote
              ? fill(t.table.auditorNote, { held: row.held, claims: row.claims, s: seconds(row.p90_ms) })
              : fill(t.table.unanswered, { held: row.held, claims: row.claims })}
        </div>
        {self && !auditorNote ? <div className="tr-sub tr-note">{t.table.selfAuditedNote}</div> : null}
        {rank !== undefined && !row.cleared ? <span className="tr-tag tr-tag--out">{t.table.notCleared}</span> : null}
      </div>
      <div role="cell" className="tr-num tr-stands" data-label={t.table.cols.stands}>
        {row.stands}
      </div>
      <div role="cell" className="tr-num tr-amended" data-label={t.table.cols.amended}>
        {row.amended}
      </div>
      <div role="cell" className="tr-num tr-overturned" data-label={t.table.cols.overturned}>
        {row.overturned}
        {row.referee_splits > 0 ? <div className="tr-sub tr-split">{fill(t.table.split, { n: row.referee_splits })}</div> : null}
      </div>
      <div role="cell" className="tr-num tr-pts" data-label={t.table.cols.pts}>
        {row.pts}
      </div>
      <div role="cell" className="tr-num" data-label={t.table.cols.clean}>
        {row.clean_pct === null || rank === undefined ? "n/a" : `${row.clean_pct}%`}
      </div>
      <div role="cell" className={`tr-trap${record && record.OVERTURNED > 0 ? " tr-overturned" : ""}`} data-label={t.table.cols.traps}>
        {record ? fill(t.table.trapsLine, { overturned: record.OVERTURNED, total: trapTotal }) : ""}
      </div>
      <div role="cell" className="tr-num" data-label={t.table.cols.p90}>
        {seconds(row.p90_ms)} s
      </div>
      <div role="cell" className="tr-cost" data-label={t.table.cols.cost}>
        <div>{price}</div>
        <div className="tr-sub">{fill(t.table.tokens, { n: compactTokens(row.tokens_per_match) })}</div>
      </div>
      <div role="cell" className="tr-failcell" data-label={t.table.cols.fail}>
        <FailBar profile={row.fail_profile} measured={rank !== undefined} />
        {top ? <div className="tr-sub tr-failtop">{fill(t.table.failTop, { bucket: t.buckets[top.bucket as keyof typeof t.buckets] ?? top.bucket, pct: Math.round(top.share * 100) })}</div> : null}
      </div>
      <div role="cell" className="tr-act">
        {cleared ? (
          <Link href={`/desk?narrator=${id}&fixture=${worst?.fixture ?? "fx-01"}`} className="tr-btn">
            {t.table.useOnDesk}
          </Link>
        ) : null}
      </div>
    </div>
  );
}

/** One row per summary row, in the export's order: measured rows by rank, then the not-ranked divider. */
export function LeagueTable() {
  const t = copy.en.trials;
  const rows = tableOrder.map((id) => summaryOf(id)).filter((r): r is SummaryRow => r !== undefined);
  const measured = rows.filter((r) => rankOf(r.candidate) !== undefined);
  const unmeasured = rows.filter((r) => rankOf(r.candidate) === undefined);
  const heads: [string, string][] = [
    ["rank", t.table.cols.rank],
    ["narrator", t.table.cols.narrator],
    ["stands", t.table.cols.stands],
    ["amended", t.table.cols.amended],
    ["overturned", t.table.cols.overturned],
    ["pts", t.table.cols.pts],
    ["clean", t.table.cols.clean],
    ["traps", t.table.cols.traps],
    ["p90", t.table.cols.p90],
    ["cost", t.table.cols.cost],
    ["fail", t.table.cols.fail],
    ["", ""],
  ];
  const per = web.results.summary[0]?.claims ?? 0;
  return (
    <div className="tr-table-wrap">
      <div className="tr-sub tr-caption">{fill(t.table.caption, { n: per })}</div>
      <div className="tr-sub tr-caption tr-caption--hint">{t.table.hint}</div>
      <div role="table" aria-label={t.table.label} className="tr-table">
        <div role="row" className="tr-row tr-head">
          {heads.map(([key, label], i) => (
            <div
              key={i}
              role="columnheader"
              title={key ? t.table.tips[key as keyof typeof t.table.tips] : undefined}
              className={`tr-hd${i >= 2 && i <= 9 ? " tr-hd--c" : ""}`}
            >
              {label}
            </div>
          ))}
        </div>
        {measured.map((r, i) => (
          <Row key={r.candidate} row={r} leader={i === 0} />
        ))}
        {unmeasured.length > 0 ? (
          <div role="row" className="tr-divider">
            <div role="cell">
              <span className="tr-hd">{t.table.incompleteNote}</span>
            </div>
          </div>
        ) : null}
        {unmeasured.map((r) => (
          <Row key={r.candidate} row={r} leader={false} />
        ))}
      </div>
    </div>
  );
}

export const candidateCount = (): number => web.results.candidates.length;
