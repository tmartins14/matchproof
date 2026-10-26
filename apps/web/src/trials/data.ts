import type { TrialsWeb } from "@/contracts/types";
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
export const clockOfWorst = (w: Worst): string => momentOf(w.fixture, w.beat)?.clock ?? "";
/** Table order: measured rows by rank, then the unmeasured rows below the divider. */
export const tableOrder: string[] = web.order;
export const firstTrapBeat = (fixture: string): string | undefined => fixtureById(fixture)?.trap_beats[0]?.beat;
/** The candidate's claim rows on a fixture, scored or not, in index order, each with the numbers the export tied to facts. */
export const cachedRowsOf = (candidate: string, fixture: string): CachedRow[] =>
  web.results.claims.flatMap((row, i) => (row.candidate === candidate && row.fixture === fixture ? [{ row, numbers: web.claim_numbers[String(i)] ?? [] }] : []));
