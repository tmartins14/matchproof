import type { MatchBrief } from "@/contracts/types";
import type { Copy } from "./copy";

export type Formation = MatchBrief["home"]["formation"];
export const formations: Formation[] = ["4-3-3", "4-2-3-1", "4-4-2", "3-5-2", "5-3-2"];

export interface SideTactics {
  formation: Formation;
  /** press, directness, line height, each 0 to 1 */
  dials: [number, number, number];
}

export interface Tactics {
  home: SideTactics;
  away: SideTactics;
}

/** Thresholds: at or above hi is band 0, at or above lo is band 1, else band 2. */
export function band(value: number, hi: number, lo: number): 0 | 1 | 2 {
  return value >= hi ? 0 : value >= lo ? 1 : 2;
}

export function bandOf(dial: number, value: number): 0 | 1 | 2 {
  if (dial === 0) return band(value, 0.7, 0.45);
  if (dial === 1) return band(value, 0.65, 0.35);
  return band(value, 0.65, 0.4);
}

export function dialWord(c: Copy, dial: number, value: number): string {
  const words = dial === 0 ? c.setup.words.press : dial === 1 ? c.setup.words.directness : c.setup.words.line;
  return words[bandOf(dial, value)] ?? "";
}

export function tacticsOf(brief: MatchBrief): Tactics {
  const side = (t: MatchBrief["home"]): SideTactics => ({ formation: t.formation, dials: [t.press, t.directness, t.line_height] });
  return { home: side(brief.home), away: side(brief.away) };
}

function teamLine(c: Copy, name: string, side: SideTactics, home: boolean): string {
  const p = c.setup.phrases;
  const [press, direct, line] = side.dials;
  const lineSet = home ? p.lineHome : p.lineAway;
  return `${name} (${side.formation}) ${p.press[bandOf(0, press)]}, ${p.directness[bandOf(1, direct)]} ${p.and} ${lineSet[bandOf(2, line)]}.`;
}

export function composeBrief(c: Copy, tactics: Tactics, storyline: string): string {
  return `${teamLine(c, c.side.home, tactics.home, true)} ${teamLine(c, c.side.away, tactics.away, false)} ${storyline}`;
}

function shortLine(c: Copy, code: string, side: SideTactics, lang: "en" | "es"): string {
  const [press, direct, line] = side.dials;
  const pressText = lang === "es" ? `${c.setup.press} ${dialWord(c, 0, press)}` : `${dialWord(c, 0, press)} ${c.setup.press}`;
  const lineText = lang === "es" ? `${c.setup.line} ${dialWord(c, 2, line)}` : `${dialWord(c, 2, line)} ${c.setup.line}`;
  return `${code} ${side.formation}, ${pressText}, ${dialWord(c, 1, direct)}, ${lineText}`;
}

export function setupSummary(c: Copy, tactics: Tactics, brief: MatchBrief, storyline: string, lang: "en" | "es"): string {
  return `${shortLine(c, brief.home.short, tactics.home, lang)} ${c.setup.versus} ${shortLine(c, brief.away.short, tactics.away, lang)} · ${storyline}`;
}
