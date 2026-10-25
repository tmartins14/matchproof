import type { Beat, Event, PositionFrame } from "@/contracts/types";
import type { DeskData, Highlight } from "./deskData";
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

/** What the lower-third on the pitch says. */
export type PitchCaption = { kind: "freeze"; t: number } | { kind: "focus" } | { kind: "live" } | { kind: "start" };

export interface PitchView {
  frame: PositionFrame | undefined;
  caption: PitchCaption | undefined;
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

interface PitchFrame {
  frame: PositionFrame | undefined;
  caption: PitchCaption | undefined;
}

const freezeOf = (frame: PositionFrame | undefined): PitchFrame => ({ frame, caption: frame ? { kind: "freeze", t: frame.t } : undefined });

/** The frame to draw and its caption. A fixture shows the selected beat's freeze frame; a live desk shows the stream. */
function frameFor(fx: DeskData, beat: Beat | undefined, pinned: boolean, startingFrame: PositionFrame | undefined): PitchFrame {
  if (fx.source === "fixture") return freezeOf(beat ? fx.frames[beat.anchor_event_id] : undefined);
  const pinnedFrame = pinned && beat ? fx.frames[beat.anchor_event_id] : undefined;
  if (pinnedFrame) return freezeOf(pinnedFrame);
  if (fx.phase === "freeze") {
    const held = (fx.freezeEventId ? fx.frames[fx.freezeEventId] : undefined) ?? fx.liveFrame;
    return freezeOf(held);
  }
  if (!fx.liveFrame) return { frame: startingFrame, caption: startingFrame ? { kind: "start" } : undefined };
  if (fx.phase === "focus") return { frame: fx.liveFrame, caption: { kind: "focus" } };
  return { frame: fx.liveFrame, caption: fx.phase === "live" ? { kind: "live" } : undefined };
}

export function buildPitch(
  fx: DeskData,
  model: DeskModel,
  eventIdsOfSelected: string[],
  eventIdsOfBeat: string[],
  pinned = false,
  startingFrame?: PositionFrame,
): PitchView {
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
  const { frame, caption } = frameFor(fx, beat, pinned, startingFrame);
  return { frame, caption, marks, highlight: beat ? fx.highlights[beat.id] : undefined, goalkeepers };
}
