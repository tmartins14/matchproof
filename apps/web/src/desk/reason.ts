import { fill, type Copy } from "./copy";

const JUDGE = /^Judge \(([^)]+)\):\s*(.*)$/s;
const VOICE = /^Voice rule ([\w-]+) broken by [^:]*:\s*(.*)$/s;
const NO_FACTS = /^The claim cites no facts\.?$/;
const OUTSIDE = /^Cited fact \S+ is not in the beat's fact bundle\.?$/;
const NUMBER = /^The number "([^"]*)" matches no display rendering of the cited facts\.?$/;
const COMPARES = /^'([^']*)' compares, but no before or change fact is cited\.?$/;
const PLAYER = /^The player "([^"]*)" is not named by any cited fact\.?$/;
const UNANSWERED = /^Judge did not answer\b/;
/** Where one reason ends and the next begins: a semicolon followed by the start of a known reason. */
const BOUNDARY = /;\s+(?=Cited fact |The number |The claim |The player |'[^']*' compares|Judge |Voice rule )/;
/** What a viewer never reads: fact, event and aggregate ids, match-clock tokens, the word bundle, snake_case. */
const INTERNAL = /\b(?:fx|ev|agg|win|ff)-|\bt\d+(?:[.-]\d+)?\b|\bbundle\b|_/i;

function one(raw: string, c: Copy): string {
  const l = c.reasonLine;
  const labels: Record<string, string> = c.reasonCategory;
  const text = raw.trim();
  if (NO_FACTS.test(text)) return l.noFacts;
  if (OUTSIDE.test(text)) return l.outsideMoment;
  const number = NUMBER.exec(text);
  if (number) return fill(l.numberNotInFacts, { n: number[1] ?? "" });
  const compares = COMPARES.exec(text);
  if (compares) return fill(l.comparison, { word: compares[1] ?? "" });
  const player = PLAYER.exec(text);
  if (player) return fill(l.player, { name: player[1] ?? "" });
  if (UNANSWERED.test(text)) return l.unanswered;
  const match = JUDGE.exec(text) ?? VOICE.exec(text);
  if (match) {
    const [, category = "", sentence = ""] = match;
    const label = labels[category] ?? c.reasonCategory.other;
    // The sentence is the judge's or the rule's own words; with an id or a machine token in it, the label stands alone.
    return sentence && !INTERNAL.test(sentence) ? `${label}: ${sentence}` : label;
  }
  return c.reasonCategory.other;
}

/** A checker reason for the desk, one line for each reason joined in it. Raw text never shows. */
export function reasonLines(raw: string, c: Copy): string[] {
  return raw
    .split(BOUNDARY)
    .filter((part) => part.trim())
    .map((part) => one(part, c));
}

/** The lines on one line, for a tooltip. */
export function displayReason(raw: string, c: Copy): string {
  return reasonLines(raw, c).join(" · ");
}
