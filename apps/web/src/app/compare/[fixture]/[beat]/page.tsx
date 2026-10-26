import { Suspense } from "react";
import { CompareView } from "@/components/trials/CompareView";
import { beatsOf, web } from "@/trials/data";

export const metadata = { title: "Matchproof Narrator Trials: Compare" };
export const dynamicParams = false;

export function generateStaticParams(): { fixture: string; beat: string }[] {
  return web.fixtures.flatMap((f) => beatsOf(f.id).map((beat) => ({ fixture: f.id, beat })));
}

export default async function Page({ params }: { params: Promise<{ fixture: string; beat: string }> }) {
  const { fixture, beat } = await params;
  return (
    <Suspense>
      <CompareView fixture={fixture} beat={beat} />
    </Suspense>
  );
}
