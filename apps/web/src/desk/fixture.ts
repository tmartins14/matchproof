import type { Beat, Claim, Event, Fact, MatchBrief, PositionFrame } from "@/contracts/types";
import raw from "../../fixtures/desk.json";
import { emptyDesk, type DeskData, type Highlight, type RunningMark, type SourceRef } from "./deskData";

/** What the fixture file holds: a snapshot of a finished match at one minute. */
export interface FixtureFile {
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
  running: RunningMark[];
  /** momentum(min-NN) fact ids in bucket order */
  momentum: string[];
}

const VERDICTS = ["checking", "verified", "rephrased", "blocked", "delayed"];

export type { Highlight, RunningMark, SourceRef };

function fail(message: string): never {
  throw new Error(`desk fixture: ${message}`);
}

/** Checks the references the desk depends on; any dangling id fails the build. */
export function validateFixture(value: unknown): FixtureFile {
  const fx = value as FixtureFile;
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
  for (const mark of fx.running) {
    for (const sides of Object.values(mark.facts)) {
      for (const id of Object.values(sides)) if (!factIds.has(id)) fail(`running mark ${mark.minute} cites unknown fact ${id}`);
    }
  }
  for (const id of fx.momentum) if (!factIds.has(id)) fail(`momentum cites unknown fact ${id}`);
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

/** The fixture as desk data: a live match frozen at its snapshot minute. */
export function fromFixture(fx: FixtureFile): DeskData {
  const base = emptyDesk(fx.brief, "fixture");
  const score = fx.score_timeline.filter((s) => s.t <= fx.snapshot.t).at(-1);
  const counts = fx.count_timeline[fx.snapshot.minute] ?? { events: 0, facts: 0 };
  return {
    ...base,
    match_id: fx.match_id,
    beats: fx.beats,
    claims: fx.claims,
    facts: fx.facts,
    events: fx.events,
    sources: fx.sources,
    frames: fx.frames,
    highlights: fx.highlights,
    ticker_event_ids: fx.ticker_event_ids,
    running: fx.running,
    momentum: fx.momentum,
    phase: "live",
    clock: fx.snapshot.t,
    score: score ? { home: score.home, away: score.away } : { home: 0, away: 0 },
    counts,
  };
}

export const fixture: DeskData = fromFixture(validateFixture(raw));
