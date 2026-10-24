import type { Claim } from "@/contracts/types";
import type { Copy } from "./copy";

export interface ClaimLine {
  label?: string;
  text: string;
}

/** The struck sentences of an overturned claim, in order: the first draft, then the rewrite. */
export function overturnedLines(claim: Claim, c: Copy): ClaimLine[] {
  if (!claim.draft_text || claim.draft_text === claim.text) return [{ text: claim.text }];
  return [
    { label: c.claim.firstDraft, text: claim.draft_text },
    { label: c.claim.rewrite, text: claim.text },
  ];
}
