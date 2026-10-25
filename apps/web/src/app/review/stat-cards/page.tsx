import { Suspense } from "react";
import { StatCardsView } from "./View";

/** Review aid: the stat card for one real fact of every metric family the registry emits. */
export default function StatCards() {
  return (
    <Suspense>
      <StatCardsView />
    </Suspense>
  );
}
