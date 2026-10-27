"use client";

import { usePathname, useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import type { MatchBrief } from "@/contracts/types";
import type { ReviewState } from "@/desk/reviewParams";
import { deskCandidates, fixtureById, fixtureIds, isLiveReady } from "@/trials/data";
import { useCachedMatch } from "@/live/useCachedMatch";
import { PAUSED_NOTICE } from "@/live/accumulate";
import { useLiveMatch, type LiveMatch } from "@/live/useLiveMatch";
import type { Failure } from "@/live/api";
import { Desk } from "./Desk";

interface TrialsDeskProps {
  initial: ReviewState;
  /** `?narrator=` and `?fixture=` as given in the URL */
  narrator?: string;
  fixture?: string;
}

const FALLBACK_REASONS: Failure[] = ["busy", "unreachable", "rate_limit"];

/** The narrator `?narrator=` names if it is cleared, else the Table leader ("" when none is). */
export function pickNarrator(wanted: string | undefined): string {
  return wanted && deskCandidates.includes(wanted) ? wanted : (deskCandidates[0] ?? "");
}

export function pickFixture(wanted: string | undefined): string {
  return wanted && fixtureIds.includes(wanted) ? wanted : (fixtureIds[0] ?? "fx-01");
}

function briefOf(fixture: string): MatchBrief {
  const f = fixtureById(fixture);
  if (!f) throw new Error(`no fixture ${fixture}`);
  return f.match_brief as unknown as MatchBrief;
}

/**
 * The Trials desk: one narrator on one pack fixture. The live narrator runs through the API; any other
 * cleared narrator replays its claims from the pack run over the recorded stream. The desk below gets
 * one `LiveMatch` either way.
 */
export function TrialsDesk({ initial, narrator: wantedNarrator, fixture: wantedFixture }: TrialsDeskProps) {
  const router = useRouter();
  const pathname = usePathname();
  const narrator = pickNarrator(wantedNarrator);
  const fixture = pickFixture(wantedFixture);
  const first = useMemo(() => briefOf(fixture), [fixture]);
  const live = useLiveMatch(first);
  const cached = useCachedMatch(first, { fixture, candidate: narrator });
  const [playing, setPlaying] = useState<"live" | "cached" | undefined>(undefined);
  // The live failure we already offered a replay for, so a new failure offers it again.
  const [dismissed, setDismissed] = useState(0);
  const liveReady = isLiveReady(narrator);
  const cachedMode = !liveReady;
  const failed = live.problem && FALLBACK_REASONS.includes(live.problem.reason) ? live.problem : undefined;
  // Narration paused by the daily token cap means a live run that airs no claims: offer the replay too.
  const paused = playing === "live" && live.data.notices.some((n) => n.text === PAUSED_NOTICE);
  const fallback = liveReady && ((failed !== undefined && failed.id !== dismissed) || paused) && playing !== "cached";

  const go = (next: { narrator: string; fixture: string }): void => {
    live.reset(briefOf(next.fixture));
    cached.reset(briefOf(next.fixture));
    setPlaying(undefined);
    const params = new URLSearchParams(window.location.search);
    params.set("narrator", next.narrator);
    params.set("fixture", next.fixture);
    router.replace(`${pathname}?${params.toString()}`, { scroll: false });
  };

  const source: LiveMatch = playing === "cached" ? cached : live;
  const controls: Omit<LiveMatch, "data"> = {
    problem: source.problem,
    randomize: live.randomize,
    compose: live.compose,
    reset: (brief) => {
      live.reset(brief);
      cached.reset(brief);
      setPlaying(undefined);
    },
    // The run is the viewer's choice: "live" streams with ?narrator=<id>, "cached" replays the pack run.
    kickoff: async (brief, speed, mode) => {
      if (cachedMode || mode === "cached") {
        setPlaying("cached");
        return cached.kickoff(brief, speed);
      }
      setPlaying("live");
      return live.kickoff(brief, speed, narrator);
    },
  };

  return (
    <Desk
      key={fixture}
      data={source.data}
      initial={initial}
      live={controls}
      trials={{
        narrator,
        fixture,
        cachedMode,
        liveReady,
        playingCached: playing === "cached",
        playingLive: playing === "live",
        streamNarrator: playing === "live" ? live.data.narrator : undefined,
        fallback,
        onNarrator: (id) => go({ narrator: id, fixture }),
        onFixture: (id) => go({ narrator, fixture: id }),
        onFallback: () => {
          if (failed) setDismissed(failed.id);
          live.reset(first);
          setPlaying("cached");
          void cached.kickoff(first, 6);
        },
      }}
    />
  );
}
