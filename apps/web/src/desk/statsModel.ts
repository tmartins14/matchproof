import type { Copy, Lang } from "./copy";
import type { DeskFixture, StatWindow } from "./fixture";
import { displayOf, windowLabel } from "./railModel";
import type { DeskModel } from "./model";

export interface StatRow {
  label: string;
  home: string;
  away: string;
  homeShare: number;
  awayShare: number;
  factIds: string[];
}

export interface StatsView {
  window: string;
  rows: StatRow[];
}

export interface MomentumBar {
  id: string;
  home: number;
  away: number;
}

export interface PipelineView {
  events: number;
  facts: number;
  beats: number;
  claims: number;
  stand: number;
  amended: number;
  overturned: number;
  checking: number;
}

/** The latest fixed window that has finished by the clock. */
function lastWindow(fx: DeskFixture, clock: number): StatWindow | undefined {
  return fx.stat_windows.filter((w) => w.t_to <= clock).at(-1);
}

export function buildStats(fx: DeskFixture, clock: number, lang: Lang, c: Copy): StatsView | undefined {
  const win = lastWindow(fx, clock);
  if (!win) return undefined;
  const byId = new Map(fx.facts.map((f) => [f.id, f]));
  const rows: StatRow[] = [];
  const defs = [
    ["possession_share", c.stats.possession],
    ["shots", c.stats.shots],
    ["xg", c.stats.xg],
  ] as const;
  for (const [metric, label] of defs) {
    const home = byId.get(win.facts[metric]?.home ?? "");
    const away = byId.get(win.facts[metric]?.away ?? "");
    if (!home || !away) continue; // no fact behind the row: leave it out
    const h = Number(home.value);
    const a = Number(away.value);
    const total = h + a || 1;
    rows.push({ label, home: displayOf(home, lang).replace(" xG", ""), away: displayOf(away, lang).replace(" xG", ""), homeShare: h / total, awayShare: a / total, factIds: [home.id, away.id] });
  }
  const anyFact = byId.get(win.facts.possession_share?.home ?? "");
  return { window: anyFact ? (windowLabel(anyFact, c) ?? "") : "", rows };
}

export function buildMomentum(fx: DeskFixture, clock: number): MomentumBar[] {
  const byId = new Map(fx.facts.map((f) => [f.id, f]));
  return fx.stat_windows
    .filter((w) => w.t_to <= clock)
    .flatMap((w) => {
      const home = byId.get(w.facts.field_tilt?.home ?? "");
      const away = byId.get(w.facts.field_tilt?.away ?? "");
      return home && away ? [{ id: w.id, home: Number(home.value), away: Number(away.value) }] : [];
    });
}

export function scoreAt(fx: DeskFixture, clock: number): { home: number; away: number } {
  const row = fx.score_timeline.filter((s) => s.t <= clock).at(-1);
  return row ? { home: row.home, away: row.away } : { home: 0, away: 0 };
}

export function buildPipeline(fx: DeskFixture, model: DeskModel): PipelineView {
  const counts = fx.count_timeline[model.minute] ?? { events: 0, facts: 0 };
  const verdicts = model.feed.flatMap((row) => row.verdicts);
  const tally = (v: string): number => verdicts.filter((x) => x === v).length;
  return {
    events: counts.events,
    facts: counts.facts,
    beats: model.revealed.length,
    claims: verdicts.length,
    stand: tally("verified"),
    amended: tally("rephrased"),
    overturned: tally("blocked"),
    checking: tally("checking"),
  };
}
