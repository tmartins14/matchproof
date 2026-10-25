import { Suspense } from "react";
import { KeyMomentsView } from "./View";

/** Review aid for the key-moment bar: every headline beside every stamp. */
export default function KeyMoments() {
  return (
    <Suspense>
      <KeyMomentsView />
    </Suspense>
  );
}
