import type { Event, PositionFrame } from "@/contracts/types";
import type { DeskFixture, Highlight } from "./fixture";
import type { DeskModel } from "./model";

export interface PitchMark {
  id: string;
  kind: "pressure" | "turnover" | "shot" | "pass" | "carry";
  side: "home" | "away";
  at: [number, number];
  to?: [number, number];
  xg?: number;
  goal?: boolean;
  dim: boolean;
}

export interface PitchView {
  frame: PositionFrame | undefined;
  marks: PitchMark[];
  highlight: Highlight | undefined;
  goalkeepers: Set<string>;
}

function markOf(event: Event, dim: boolean): PitchMark | undefined {
  const base = { id: event.id, side: event.side, at: event.location, dim };
  switch (event.type) {
    case "pressure":
      return { ...base, kind: "pressure" };
    case "interception":
    case "tackle":
      return { ...base, kind: "turnover" };
    case "shot":
      return { ...base, kind: "shot", xg: event.shot?.xg, goal: event.outcome === "goal", to: event.end_location };
    case "pass":
    case "carry":
      return event.end_location ? { ...base, kind: event.type, to: event.end_location } : undefined;
    default:
      return undefined;
  }
}

export function buildPitch(fx: DeskFixture, model: DeskModel, eventIdsOfSelected: string[], eventIdsOfBeat: string[]): PitchView {
  const beat = model.selectedBeat;
  const eventById = new Map(fx.events.map((e) => [e.id, e]));
  const selected = new Set(eventIdsOfSelected);
  const marks = [...new Set([...eventIdsOfBeat, ...eventIdsOfSelected])].flatMap((id) => {
    const event = eventById.get(id);
    const mark = event && markOf(event, !selected.has(id) && selected.size > 0);
    return mark ? [mark] : [];
  });
  const goalkeepers = new Set(
    [...fx.brief.home.players, ...fx.brief.away.players].filter((p) => p.slot === 0).map((p) => p.id),
  );
  return {
    frame: beat ? fx.frames[beat.anchor_event_id] : undefined,
    marks,
    highlight: beat ? fx.highlights[beat.id] : undefined,
    goalkeepers,
  };
}
