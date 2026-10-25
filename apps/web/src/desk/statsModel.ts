import type { Copy, Lang } from "./copy";
import { fill } from "./copy";
import type { DeskFixture, RunningMark } from "./fixture";
import { displayOf } from "./railModel";
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
  /** 0-based bucket, the slot the bar fills */
  slot: number;
  factId: string;
  /** the fact's value, percentage points from -100 to 100 */
  value: number;
  /** value over the largest absolute value so far, -1 to 1: a rendering of the fact, not a statistic */
  scale: number;
}

export const MOMENTUM_SLOTS = 18;

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

/** The latest 5-minute mark that has closed by the clock. */
function lastMark(fx: DeskFixture, clock: number): RunningMark | undefined {
  return fx.running.filter((m) => m.t_to <= clock).at(-1);
}

export function buildStats(fx: DeskFixture, clock: number, lang: Lang, c: Copy): StatsView | undefined {
  const mark = lastMark(fx, clock);
  if (!mark) return undefined;
  const byId = new Map(fx.facts.map((f) => [f.id, f]));
  const rows: StatRow[] = [];
  const defs = [
    ["possession_share", c.stats.possession],
    ["shots", c.stats.shots],
    ["shots_on_target", c.stats.shotsOnTarget],
    ["xg", c.stats.xg],
  ] as const;
  for (const [metric, label] of defs) {
    const home = byId.get(mark.facts[metric]?.home ?? "");
    const away = byId.get(mark.facts[metric]?.away ?? "");
    if (!home || !away) continue; // no fact behind the row: leave it out
    const h = Number(home.value);
    const a = Number(away.value);
    const total = h + a || 1;
    rows.push({ label, home: displayOf(home, lang).replace(" xG", ""), away: displayOf(away, lang).replace(" xG", ""), homeShare: h / total, awayShare: a / total, factIds: [home.id, away.id] });
  }
  return { window: fill(c.stats.toMinute, { minute: mark.minute }), rows };
}

/** One bar per momentum fact whose bucket has closed by the clock. */
export function buildMomentum(fx: DeskFixture, clock: number): MomentumBar[] {
  const byId = new Map(fx.facts.map((f) => [f.id, f]));
  const closed = fx.momentum.flatMap((id, slot) => {
    const fact = byId.get(id);
    return fact && (fact.scope?.t_to ?? Infinity) <= clock ? [{ slot, factId: id, value: Number(fact.value) }] : [];
  });
  const peak = Math.max(...closed.map((b) => Math.abs(b.value)), 0);
  return closed.map((b) => ({ ...b, scale: peak === 0 ? 0 : b.value / peak }));
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
