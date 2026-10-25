import type { Beat, Claim, Event, Fact, MatchBrief, PositionFrame } from "@/contracts/types";

export type SourceRef =
  | { kind: "aggregate"; description: string }
  | { kind: "window"; t_from: number; t_to: number }
  | { kind: "freeze_frame"; event_id: string };

export interface Highlight {
  player_ids?: string[];
  zone?: { x_from: number; x_to: number };
}

export type RunningMetric = "possession_share" | "shots" | "shots_on_target" | "xg";

/** The match-to-date facts at one 5-minute mark. */
export interface RunningMark {
  minute: number;
  t_to: number;
  facts: Partial<Record<RunningMetric, Partial<Record<"home" | "away", string>>>>;
}

export type Phase = "pre" | "connecting" | "live" | "focus" | "freeze" | "half_time" | "full_time" | "error";

export interface ViewerNotice {
  id: number;
  text: string;
}

/**
 * Everything the desk draws. The static fixture is one source of it and the live accumulator is the
 * other; the builders (model, statsModel, railModel, pitchModel) take this and nothing else.
 */
export interface DeskData {
  source: "fixture" | "live";
  match_id: string;
  brief: MatchBrief;
  players: Record<string, { name: string; number: number }>;
  beats: Beat[];
  claims: Claim[];
  facts: Fact[];
  events: Event[];
  sources: Record<string, SourceRef>;
  frames: Record<string, PositionFrame>;
  highlights: Record<string, Highlight>;
  ticker_event_ids: string[];
  running: RunningMark[];
  /** momentum(min-NN) fact ids by bucket; a bucket not yet sent is undefined */
  momentum: (string | undefined)[];
  phase: Phase;
  /** the latest message's match second */
  clock: number;
  /** the score as the server last sent it */
  score: { home: number; away: number };
  /** messages received, for the pipeline strip */
  counts: { events: number; facts: number };
  liveFrame: PositionFrame | undefined;
  /** the anchor event of the freeze in progress */
  freezeEventId: string | undefined;
  /** cruising speed from the stream's statuses */
  speed: number | undefined;
  notices: ViewerNotice[];
  /** lookups the accumulator keeps; claim id to its slot in `claims`, fact ids already stored */
  claimSlot: Map<string, number>;
  factIds: Set<string>;
  awaitingFreezeFrame: boolean;
}

export function playersOf(brief: MatchBrief): DeskData["players"] {
  return Object.fromEntries([...brief.home.players, ...brief.away.players].map((p) => [p.id, { name: p.name, number: p.number }]));
}

export function emptyDesk(brief: MatchBrief, source: DeskData["source"]): DeskData {
  return {
    source,
    match_id: brief.match_id,
    brief,
    players: playersOf(brief),
    beats: [],
    claims: [],
    facts: [],
    events: [],
    sources: {},
    frames: {},
    highlights: {},
    ticker_event_ids: [],
    running: [],
    momentum: Array.from({ length: 18 }, () => undefined),
    phase: "pre",
    clock: 0,
    score: { home: 0, away: 0 },
    counts: { events: 0, facts: 0 },
    liveFrame: undefined,
    freezeEventId: undefined,
    speed: undefined,
    notices: [],
    claimSlot: new Map(),
    factIds: new Set(),
    awaitingFreezeFrame: false,
  };
}
