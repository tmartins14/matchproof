import type { MatchBrief, PositionFrame } from "@/contracts/types";
import raw from "../../fixtures/setup.json";

type Point = [number, number];

interface SetupFile {
  storylines: Record<string, { text: string; planted_beats: MatchBrief["planted_beats"] }>;
  /** formation to each side's 11 slot positions, from scripts/make_setup_data.py */
  shapes: Record<string, { home: Point[]; away: Point[] }>;
}

export const setupData = raw as unknown as SetupFile;

/** The brief's starting shape as a frame, from the simulator's own slot positions. */
export function startingFrame(brief: MatchBrief, setup: SetupFile = setupData): PositionFrame {
  const players = (["home", "away"] as const).flatMap((side) => {
    const team = brief[side];
    const slots = setup.shapes[team.formation]?.[side] ?? [];
    return team.players.slice(0, 11).flatMap((p) => {
      const at = slots[p.slot];
      return at ? [{ id: p.id, side, at }] : [];
    });
  });
  return { match_id: brief.match_id, t: 0, ball: [60, 40], players };
}
