import type { Fact } from "@/contracts/types";
import type { Copy, Lang } from "./copy";
import { fill } from "./copy";
import type { DeskFixture } from "./fixture";
import { formatClock, formatMinute } from "./format";

export interface RailEvent {
  id: string;
  label: string;
  who: string;
  time: string;
  side?: "home" | "away";
  /** an event shows its id; a window, aggregate or freeze frame shows what it covers, with the id in the title */
  isEvent: boolean;
}

export interface FactLine {
  factId: string;
  label: string;
  value: string;
  name: string;
}

export interface StatCardView {
  value: string;
  metric: string;
  factId: string;
  window?: string;
}

export interface RailView {
  factLines: FactLine[];
  events: RailEvent[];
  statCard?: StatCardView;
}

export function displayOf(fact: Fact, lang: Lang): string {
  return (fact.display[lang] ?? fact.display.en)[0] ?? String(fact.value);
}

/** The shortest accepted rendering, for the stat card where the number is shown large. */
export function shortDisplayOf(fact: Fact, lang: Lang): string {
  const options = fact.display[lang] ?? fact.display.en;
  return options.reduce((best, next) => (next.length < best.length ? next : best), options[0] ?? String(fact.value));
}

/** copy.metric key for a fact name such as shot(ev-000222).xg or xg(home, win-04). */
export function metricKey(name: string): string {
  return name.replace(/\([^)]*\)/, "");
}

export function windowLabel(fact: Fact, c: Copy): string | undefined {
  const scope = fact.scope;
  if (scope?.t_from === undefined || scope.t_to === undefined) return undefined;
  const from = formatMinute(scope.t_from);
  const to = formatMinute(scope.t_to);
  return from === to ? undefined : fill(c.stats.window, { from, to });
}

function metricLabel(fact: Fact, c: Copy, sideFallback?: "home" | "away"): string {
  const key = metricKey(fact.name) as keyof Copy["metric"];
  const label = c.metric[key] ?? key;
  const side = fact.scope?.side ?? sideFallback;
  return side ? `${label} · ${c.side[side]}` : label;
}

const isHeadline = (f: Fact): boolean => f.unit === "m" || f.unit === "count" || f.name.startsWith("score_after");

/** The claim's first number a viewer reads as the point: a distance, count or score before a duration. */
export function pickLead(facts: Fact[]): Fact | undefined {
  return facts.find(isHeadline) ?? facts.find((f) => f.unit !== "s") ?? facts[0];
}

export function buildRail(fx: DeskFixture, claimFactIds: string[], numberFactIds: string[], lang: Lang, c: Copy, side?: "home" | "away"): RailView {
  const factById = new Map(fx.facts.map((f) => [f.id, f]));
  const facts = [...new Set([...claimFactIds, ...numberFactIds])].flatMap((id) => factById.get(id) ?? []);
  const factLines = facts.map((f) => ({ factId: f.id, label: f.label ?? f.name, value: displayOf(f, lang), name: f.name }));

  const eventById = new Map(fx.events.map((e) => [e.id, e]));
  const sourceIds = [...new Set(facts.flatMap((f) => f.source_ids))];
  const events = sourceIds.map((id): RailEvent => {
    const event = eventById.get(id);
    if (event) {
      const name = event.player_id ? (fx.players[event.player_id]?.name ?? event.player_id) : "";
      return { id, label: c.eventType[event.type], who: name, time: formatClock(event.t), side: event.side, isEvent: true };
    }
    const source = fx.sources[id];
    if (source?.kind === "window") {
      return { id, label: c.rail.window, who: `${formatClock(source.t_from)}–${formatClock(source.t_to)}`, time: "", isEvent: false };
    }
    if (source?.kind === "freeze_frame") return { id, label: c.rail.freezeFrame, who: source.event_id, time: "", isEvent: false };
    return { id, label: c.rail.aggregate, who: source?.kind === "aggregate" ? source.description : "", time: "", isEvent: false };
  });

  const lead = pickLead(numberFactIds.flatMap((id) => factById.get(id) ?? []));
  const statCard = lead
    ? { value: shortDisplayOf(lead, lang), metric: metricLabel(lead, c, side), factId: lead.id, window: windowLabel(lead, c) }
    : undefined;
  return { factLines, events, statCard };
}
