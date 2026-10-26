import type { ClaimRow } from "./data";

/** 1900 -> "1.9". */
export const seconds = (ms: number): string => (ms / 1000).toFixed(1);

/** "fx-03" -> "03". */
export const fixtureNumber = (id: string): string => id.replace(/^fx-/, "");

/** "2026-10-26T13:44:29Z" -> "2026-10-26". */
export const runDate = (iso: string): string => iso.slice(0, 10);

/** 1_500_000 -> "1.5M", 91_000 -> "91k". */
export function compactTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${Math.round(n / 1_000)}k`;
  return String(n);
}

export type VerdictKey = "verified" | "rephrased" | "blocked" | "delayed";
const KEY: Record<ClaimRow["verdict"], VerdictKey> = { STANDS: "verified", AMENDED: "rephrased", OVERTURNED: "blocked", HELD: "delayed" };
/** The Desk's verdict key for a Trials verdict, so the existing stamp and tokens apply. */
export const verdictKey = (v: ClaimRow["verdict"]): VerdictKey => KEY[v];

/** "Judge (overclaim): x" and "Second reviewer (wrong_entity): x" read as "x". */
export const plainReason = (reason: string): string => reason.replace(/^(?:Judge|Second reviewer) \([^)]*\):\s*/, "");

/** "<bucket>: <reason>" for the first reason of a claim, or undefined when it has none. */
export function reasonLine(row: Pick<ClaimRow, "reason_bucket" | "reasons">): string | undefined {
  const first = row.reasons[0];
  if (!first) return undefined;
  return row.reason_bucket ? `${row.reason_bucket}: ${plainReason(first)}` : plainReason(first);
}

export interface AmendedParts {
  before: string;
  failed: string;
  corrected: string;
  after: string;
}

/**
 * Splits the draft around the words that changed. Returns undefined unless the pieces put back together
 * give exactly the aired text, so the card never shows a diff that does not match what went to air.
 */
export function amendedParts(row: Pick<ClaimRow, "draft_text" | "text" | "failed_span" | "corrected_span">): AmendedParts | undefined {
  const { draft_text: draft, text, failed_span: failed, corrected_span: corrected } = row;
  if (!failed || !corrected) return undefined;
  const at = draft.indexOf(failed);
  if (at < 0) return undefined;
  const before = draft.slice(0, at);
  const after = draft.slice(at + failed.length);
  return before + corrected + after === text ? { before, failed, corrected, after } : undefined;
}

/** Pairs each fail-profile bucket with its share, biggest first, for the bar and its legend. */
export function failParts(profile: Record<string, number>): { bucket: string; share: number }[] {
  return Object.entries(profile)
    .map(([bucket, share]) => ({ bucket, share }))
    .sort((a, b) => b.share - a.share);
}
