"use client";

import { usePathname, useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import type { MatchBrief } from "@/contracts/types";
import type { ReviewState } from "@/desk/reviewParams";
import { deskCandidates, fixtureById, fixtureIds, liveNarrator } from "@/trials/data";
import { useCachedMatch } from "@/live/useCachedMatch";
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
  const cachedMode = narrator !== liveNarrator;
  const failed = live.problem && FALLBACK_REASONS.includes(live.problem.reason) ? live.problem : undefined;
  const fallback = !cachedMode && failed !== undefined && failed.id !== dismissed && playing !== "cached";

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
    kickoff: async (brief, speed) => {
      if (cachedMode) {
        setPlaying("cached");
        return cached.kickoff(brief, speed);
      }
      setPlaying("live");
      return live.kickoff(brief, speed);
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
        playingCached: playing === "cached",
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
