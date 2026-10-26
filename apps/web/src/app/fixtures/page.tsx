import { Suspense } from "react";
import { FixturesPage } from "@/components/trials/FixturesPage";

export const metadata = { title: "Matchproof Narrator Trials: Fixtures" };

export default function Page() {
  return (
    <Suspense>
      <FixturesPage />
    </Suspense>
  );
}
