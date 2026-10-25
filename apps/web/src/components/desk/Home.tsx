"use client";

import { useSearchParams } from "next/navigation";
import { fixture } from "@/desk/fixture";
import { parseReviewParams } from "@/desk/reviewParams";
import { Desk } from "./Desk";
import { LiveDesk } from "./LiveDesk";

/** Reads the URL on the client, since the export is static. Live is the default. */
export function Home() {
  const search = useSearchParams();
  const params = Object.fromEntries(search.entries());
  // ?source=fixture shows the static fixture for review; the review parameters apply only there.
  if (params.source === "fixture") {
    const initial = parseReviewParams(params);
    const labels = initial.labels;
    // Labelled rows must all show, so the clock moves on to the last labelled beat.
    const reveal = labels ? (fixture.beats[labels.length - 1]?.t_detect ?? 0) : 0;
    const data = labels ? { ...fixture, clock: Math.max(fixture.clock, reveal), beats: fixture.beats.map((b, i) => ({ ...b, label: labels[i] ?? b.label })) } : fixture;
    return <Desk data={data} initial={initial} />;
  }
  return <LiveDesk initial={parseReviewParams({ lang: params.lang, mode: params.mode })} />;
}
