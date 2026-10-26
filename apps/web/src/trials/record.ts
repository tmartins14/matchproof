import type { ClaimRow } from "./data";

export type RecordVerdict = ClaimRow["verdict"] | "CHECKING";

export interface RecordView {
  STANDS: number;
  AMENDED: number;
  OVERTURNED: number;
  CHECKING: number;
  pts: number;
}

/**
 * The RECORD tile: counts of the first claim of each beat that has landed so far, and their points on
 * the Table's scale. It only adds up claims already on screen, with the scale the export carries, so
 * it agrees with the Table's scoring; it works out nothing about football (seam rule 3). HELD scores
 * what the scale says and has no count of its own.
 */
export function recordOf(landed: RecordVerdict[], points: Record<ClaimRow["verdict"], number>): RecordView {
  const view: RecordView = { STANDS: 0, AMENDED: 0, OVERTURNED: 0, CHECKING: 0, pts: 0 };
  for (const verdict of landed) {
    if (verdict === "CHECKING") view.CHECKING += 1;
    else {
      if (verdict !== "HELD") view[verdict] += 1;
      view.pts += points[verdict];
    }
  }
  return view;
}

const TRIAL: Record<string, RecordVerdict> = { checking: "CHECKING", verified: "STANDS", rephrased: "AMENDED", blocked: "OVERTURNED", delayed: "HELD" };

/** The first claim of each beat (id ending `-01`), as the Table verdict it counts as. */
export function landedOf(claims: { id: string; verdict: string }[], tableVerdicts?: ReadonlyMap<string, ClaimRow["verdict"]>): RecordVerdict[] {
  const out: RecordVerdict[] = [];
  for (const claim of claims) {
    const scored = tableVerdicts ? tableVerdicts.has(claim.id) : claim.id.endsWith("-01");
    if (!scored) continue;
    // A cached claim is checking until its verdict lands; then the Table's own verdict applies.
    out.push(claim.verdict === "checking" ? "CHECKING" : (tableVerdicts?.get(claim.id) ?? TRIAL[claim.verdict] ?? "CHECKING"));
  }
  return out;
}

/** "+3 pts", "-6 pts", "0 pts". */
export const signedPts = (pts: number): string => (pts > 0 ? `+${pts}` : pts < 0 ? `−${Math.abs(pts)}` : "0");
