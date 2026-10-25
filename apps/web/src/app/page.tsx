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
  if (params.source === "fixture") return <Desk data={fixture} initial={parseReviewParams(params)} />;
  return <LiveDesk initial={parseReviewParams({ lang: params.lang, mode: params.mode })} />;
}
