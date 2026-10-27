import type { TrialsWeb } from "@/contracts/types";
import { copy } from "@/desk/copy";
import type { CachedRow } from "@/live/cached";
import raw from "../../fixtures/trials/web-pack-v1.json";

/**
 * The one place the Trials pages read their data. Lookups only: ranks, worst moments, picks and clocks
 * are worked out in Python (evals/trials_web.py), the browser draws them (seam rule 3).
 *
 * This is the full pack. The smoke export (`web-pack-v1-smoke.json`) is not bundled; switching to it is
 * this import and `isSmoke`.
 */
export const web = raw as unknown as TrialsWeb;
export const isSmoke = false;

export type Results = TrialsWeb["results"];
export type SummaryRow = Results["summary"][number];
export type ClaimRow = Results["claims"][number];
export type Candidate = Results["candidates"][number];
export type Fixture = TrialsWeb["fixtures"][number];
export type Moment = TrialsWeb["moments"][string][string];
export type Worst = NonNullable<TrialsWeb["worst"][string]>;

export const trapRecordOf = (id: string): TrialsWeb["trap_record"][string] | undefined => web.trap_record[id];
export const failTopOf = (id: string): TrialsWeb["fail_top"][string] => web.fail_top[id] ?? null;
export const summaryOf = (id: string): SummaryRow | undefined => web.results.summary.find((r) => r.candidate === id);
export const candidateById = (id: string): Candidate | undefined => web.results.candidates.find((c) => c.id === id);
export const rankOf = (id: string): number | undefined => web.ranks[id];
export const isMeasured = (id: string): boolean => web.measured[id] === true;
export const worstOf = (id: string): Worst | null => web.worst[id] ?? null;
export const fixtureById = (id: string): Fixture | undefined => web.fixtures.find((f) => f.id === id);
export const momentOf = (fixture: string, beat: string): Moment | undefined => web.moments[fixture]?.[beat];
/** Beat ids of a fixture in play order (the export writes them sorted by detection time). */
export const beatsOf = (fixture: string): string[] => Object.keys(web.moments[fixture] ?? {});
/** The candidate's scored claim on a beat. */
export const scoredClaim = (candidate: string, fixture: string, beat: string): ClaimRow | undefined =>
  web.results.claims.find((c) => c.candidate === candidate && c.fixture === fixture && c.beat === beat && c.scored);
/** The word-level diff of an AMENDED claim, draft to aired text, as the export wrote it; undefined for any other row. */
export const diffOf = (row: ClaimRow): TrialsWeb["claim_diff"][string] | undefined => web.claim_diff[String(web.results.claims.indexOf(row))];
export const clockOfWorst = (w: Worst): string => momentOf(w.fixture, w.beat)?.clock ?? "";
/** Table order: measured rows by rank, then the unmeasured rows below the divider. */
export const tableOrder: string[] = web.order;
export const firstTrapBeat = (fixture: string): string | undefined => fixtureById(fixture)?.trap_beats[0]?.beat;
/** The candidate's claim rows on a fixture, scored or not, in index order, each with the numbers the export tied to facts. */
export const cachedRowsOf = (candidate: string, fixture: string): CachedRow[] =>
  web.results.claims.flatMap((row, i) => (row.candidate === candidate && row.fixture === fixture ? [{ row, numbers: web.claim_numbers[String(i)] ?? [] }] : []));

/** The narrators the Desk offers: measured and cleared for air, in Table order. Nobody else is listed. */
export const deskCandidates: string[] = tableOrder.filter((id) => isMeasured(id) && summaryOf(id)?.cleared === true);
export const liveNarrator: string | null = web.live_narrator;
export const fixtureIds: string[] = web.fixtures.map((f) => f.id);
/** The trap chips of a fixture, in trap order: what the trap is and its clock, such as `RED CARD 61′`. */
export const trapLabels = (fixture: string): string[] => (fixtureById(fixture)?.traps ?? []).map((t) => t.label);
/** The Compare page for a beat of a pack fixture, or undefined when the export has no such moment. */
export const compareHref = (fixture: string, beat: string, focus: string): string | undefined =>
  momentOf(fixture, beat) ? `/compare/${fixture}/${beat}?focus=${focus}` : undefined;
/** Claim id to Table verdict, for the candidate's scored rows on a fixture. */
export const scoredVerdicts = (candidate: string, fixture: string): Map<string, ClaimRow["verdict"]> =>
  new Map(web.results.claims.filter((c) => c.candidate === candidate && c.fixture === fixture && c.scored).map((c) => [c.id, c.verdict]));

/** One Fixtures cell: the Table's verdict for the row, and why a lost row got it. */
export interface Cell {
  verdict: ClaimRow["verdict"];
  /** HELD because the model call failed: the stamp reads NO ANSWER */
  noAnswer: boolean;
  /** plain English for a lost row that was overturned (tooltip and subtext) */
  why?: string;
}

/** The cell for a candidate on a beat, from its scored row; undefined when there is none. */
export function cellOf(candidate: string, fixture: string, beat: string): Cell | undefined {
  const row = scoredClaim(candidate, fixture, beat);
  if (!row) return undefined;
  return { verdict: row.verdict, noAnswer: row.lost === "no_answer", why: row.lost && row.lost !== "no_answer" ? copy.en.trials.lostReason[row.lost] : undefined };
}
