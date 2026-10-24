import type { Copy } from "./copy";

const JUDGE = /^Judge \(([^)]+)\):\s*(.*)$/s;
const VOICE = /^Voice rule ([\w-]+) broken by [^:]*:\s*(.*)$/s;
const INTERNAL = /\bjudge\b|voice rule/i;

/** A checker reason for the desk: a short category label from copy, then the sentence after the prefix. */
export function displayReason(raw: string, c: Copy): string {
  const match = JUDGE.exec(raw) ?? VOICE.exec(raw);
  const labels: Record<string, string> = c.reasonCategory;
  if (match) {
    const [, category = "", sentence = ""] = match;
    return `${labels[category] ?? c.reasonCategory.other}: ${sentence}`;
  }
  return INTERNAL.test(raw) ? c.reasonCategory.other : raw;
}
