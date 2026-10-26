"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { MatchBrief, StreamMessage } from "@/contracts/types";
import { emptyDesk, type DeskData } from "@/desk/deskData";
import { cachedRowsOf } from "@/trials/data";
import { accumulate } from "./accumulate";
import { buildTimeline, CachedPlayer, loadRecording } from "./cached";
import type { LiveMatch, Problem } from "./useLiveMatch";

/** What a cached replay plays: one candidate's pack-run claims on one fixture's recording. */
export interface CachedSource {
  fixture: string;
  candidate: string;
}

/** Recorded streams run at 6×; the desk's speed control is off in cached mode. */
export const CACHED_SPEED = 6;

/**
 * The cached desk: the same `LiveMatch` shape as `useLiveMatch`, fed by a static recording and the
 * candidate's claims from the pack run. Needs no API. Stop, reset and unmount cancel the loop.
 */
export function useCachedMatch(initial: MatchBrief, source: CachedSource): LiveMatch {
  const [data, setData] = useState<DeskData>(() => emptyDesk(initial, "live"));
  const dataRef = useRef<DeskData>(data);
  const [problem, setProblem] = useState<Problem | undefined>(undefined);
  const player = useRef<CachedPlayer | undefined>(undefined);
  const run = useRef(0);
  const problems = useRef(0);
  const sourceRef = useRef(source);
  sourceRef.current = source;

  const publish = useCallback((next: DeskData): void => {
    dataRef.current = next;
    setData(next);
  }, []);

  const stop = useCallback((): void => {
    run.current += 1; // a recording still loading is dropped
    player.current?.stop();
    player.current = undefined;
  }, []);

  useEffect(() => stop, [stop]);

  const reset = useCallback(
    (brief: MatchBrief): void => {
      stop();
      publish(emptyDesk(brief, "live"));
    },
    [publish, stop],
  );

  const kickoff = useCallback(
    async (brief: MatchBrief): Promise<MatchBrief | undefined> => {
      stop();
      const mine = run.current;
      const { fixture, candidate } = sourceRef.current;
      publish({ ...emptyDesk(brief, "live"), phase: "connecting", speed: CACHED_SPEED });
      try {
        const lines = await loadRecording(fixture);
        if (mine !== run.current) return undefined;
        const timeline = buildTimeline(lines, cachedRowsOf(candidate, fixture));
        const next = new CachedPlayer(
          timeline,
          (batch: StreamMessage[]) => publish(batch.reduce(accumulate, dataRef.current)),
          () => {
            player.current = undefined;
          },
        );
        player.current = next;
        next.start();
        return brief;
      } catch {
        if (mine !== run.current) return undefined;
        reset(brief);
        problems.current += 1;
        setProblem({ id: problems.current, reason: "unreachable" });
        return undefined;
      }
    },
    [publish, reset, stop],
  );

  return {
    data,
    problem,
    kickoff,
    reset,
    randomize: async () => ({ ok: false, reason: "rejected" }),
    compose: async () => ({ ok: false, reason: "rejected" }),
  };
}
