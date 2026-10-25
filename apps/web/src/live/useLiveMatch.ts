"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { MatchBrief, StreamMessage } from "@/contracts/types";
import { emptyDesk, type DeskData } from "@/desk/deskData";
import { accumulate } from "./accumulate";
import { composeBrief, createMatch, randomMatch, streamUrl, type Composed, type Failure, type Result } from "./api";
import { openStream } from "./stream";

export type Speed = 1 | 3 | 6;

/** A failure the desk should tell the viewer about; the id lets the same failure show twice. */
export interface Problem {
  id: number;
  reason: Failure;
}

export interface LiveMatch {
  data: DeskData;
  problem: Problem | undefined;
  /** Posts the brief, opens the stream and returns the brief under the id the server gave it. */
  kickoff: (brief: MatchBrief, speed: Speed) => Promise<MatchBrief | undefined>;
  /** Closes the stream and clears the desk; the caller keeps the brief. */
  reset: (brief: MatchBrief) => void;
  randomize: () => Promise<Result<{ match_id: string; brief: MatchBrief }>>;
  compose: (text: string) => Promise<Result<Composed>>;
}

/**
 * The live desk's state: messages are queued as they arrive and folded into the desk data once per
 * animation frame, so a stream of ten frames a second renders at most once per frame.
 */
export function useLiveMatch(initial: MatchBrief): LiveMatch {
  const [data, setData] = useState<DeskData>(() => emptyDesk(initial, "live"));
  const dataRef = useRef<DeskData>(data);
  const [problem, setProblem] = useState<Problem | undefined>(undefined);
  const queue = useRef<StreamMessage[]>([]);
  const frame = useRef<number | undefined>(undefined);
  const close = useRef<(() => void) | undefined>(undefined);
  const received = useRef(0);
  const problems = useRef(0);

  const publish = useCallback((next: DeskData): void => {
    dataRef.current = next;
    setData(next);
  }, []);

  const flush = useCallback((): void => {
    frame.current = undefined;
    const batch = queue.current.splice(0);
    if (batch.length > 0) publish(batch.reduce(accumulate, dataRef.current));
  }, [publish]);

  const enqueue = useCallback(
    (message: StreamMessage): void => {
      queue.current.push(message);
      received.current += 1;
      frame.current ??= requestAnimationFrame(flush);
    },
    [flush],
  );

  const stop = useCallback((): void => {
    close.current?.();
    close.current = undefined;
    queue.current = [];
    if (frame.current !== undefined) cancelAnimationFrame(frame.current);
    frame.current = undefined;
  }, []);

  useEffect(() => stop, [stop]);

  const fail = useCallback((reason: Failure): void => {
    problems.current += 1;
    setProblem({ id: problems.current, reason });
  }, []);

  const reset = useCallback(
    (brief: MatchBrief): void => {
      stop();
      publish(emptyDesk(brief, "live"));
    },
    [publish, stop],
  );

  const kickoff = useCallback(
    async (brief: MatchBrief, speed: Speed): Promise<MatchBrief | undefined> => {
      stop();
      received.current = 0;
      publish({ ...emptyDesk(brief, "live"), phase: "connecting", speed });
      const made = await createMatch(brief);
      if (!made.ok) {
        reset(brief);
        fail(made.reason);
        return undefined;
      }
      const played = { ...brief, match_id: made.value.match_id };
      publish({ ...emptyDesk(played, "live"), phase: "connecting", speed });
      close.current = openStream(streamUrl(played.match_id, speed), {
        onMessage: enqueue,
        onRefused: (reason) => {
          stop();
          if (received.current === 0) reset(played);
          fail(reason);
        },
        onEnd: () => {
          flush();
          if (dataRef.current.phase !== "full_time") publish({ ...dataRef.current, phase: "error" });
        },
      });
      return played;
    },
    [enqueue, fail, flush, publish, reset, stop],
  );

  return { data, problem, kickoff, reset, randomize: randomMatch, compose: composeBrief };
}
