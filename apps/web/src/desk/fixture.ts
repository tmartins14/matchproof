import type { Beat, Claim, Event, Fact, MatchBrief, PositionFrame } from "@/contracts/types";
import raw from "../../fixtures/desk.json";

export type SourceRef =
  | { kind: "aggregate"; description: string }
  | { kind: "window"; t_from: number; t_to: number }
  | { kind: "freeze_frame"; event_id: string };

export interface Highlight {
  player_ids?: string[];
  zone?: { x_from: number; x_to: number };
}

export interface StatWindow {
  id: string;
  t_from: number;
  t_to: number;
  facts: Partial<Record<"possession_share" | "shots" | "xg" | "field_tilt", Partial<Record<"home" | "away", string>>>>;
}

export interface DeskFixture {
  match_id: string;
  provenance: { archive: string; claims: string };
  brief: MatchBrief;
  final_score: { home: number; away: number };
  snapshot: { minute: number; t: number };
  players: Record<string, { name: string; number: number }>;
  beats: Beat[];
  claims: Claim[];
  facts: Fact[];
  events: Event[];
  sources: Record<string, SourceRef>;
  frames: Record<string, PositionFrame>;
  highlights: Record<string, Highlight>;
  ticker_event_ids: string[];
  score_timeline: { t: number; home: number; away: number; fact_id: string }[];
  count_timeline: { minute: number; events: number; facts: number }[];
  stat_windows: StatWindow[];
}

const VERDICTS = ["checking", "verified", "rephrased", "blocked", "delayed"];

function fail(message: string): never {
  throw new Error(`desk fixture: ${message}`);
}

/** Checks the references the desk depends on; any dangling id fails the build. */
export function validateFixture(value: unknown): DeskFixture {
  const fx = value as DeskFixture;
  if (!fx || typeof fx !== "object") fail("not an object");
  const beatIds = new Set(fx.beats.map((b) => b.id));
  const factIds = new Set(fx.facts.map((f) => f.id));
  const eventIds = new Set(fx.events.map((e) => e.id));
  for (const claim of fx.claims) {
    if (!beatIds.has(claim.beat_id)) fail(`claim ${claim.id} cites unknown beat ${claim.beat_id}`);
    if (!VERDICTS.includes(claim.verdict)) fail(`claim ${claim.id} has verdict ${claim.verdict}`);
    if (claim.verdict === "rephrased" && !claim.draft_text) fail(`claim ${claim.id} is rephrased with no draft_text`);
    for (const id of [...claim.fact_ids, ...claim.numbers.map((n) => n.fact_id)]) {
      if (!factIds.has(id)) fail(`claim ${claim.id} cites unknown fact ${id}`);
    }
  }
  for (const fact of fx.facts) {
    for (const source of fact.source_ids) {
      if (!eventIds.has(source) && !(source in fx.sources)) fail(`fact ${fact.id} cites unknown source ${source}`);
    }
  }
  for (const beat of fx.beats) {
    if (!(beat.anchor_event_id in fx.frames)) fail(`beat ${beat.id} has no freeze frame`);
  }
  for (const id of fx.ticker_event_ids) if (!eventIds.has(id)) fail(`ticker event ${id} missing`);
  return fx;
}

export const fixture: DeskFixture = validateFixture(raw);
