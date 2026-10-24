import { Desk } from "@/components/desk/Desk";
import { fixture } from "@/desk/fixture";
import { parseReviewParams } from "@/desk/reviewParams";

interface PageProps {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}

export default async function Home({ searchParams }: PageProps) {
  const initial = parseReviewParams(await searchParams);
  return <Desk fixture={fixture} initial={initial} />;
}
