import { Desk } from "@/components/desk/Desk";
import { LiveDesk } from "@/components/desk/LiveDesk";
import { fixture } from "@/desk/fixture";
import { parseReviewParams } from "@/desk/reviewParams";

interface PageProps {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}

export default async function Home({ searchParams }: PageProps) {
  const params = await searchParams;
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
