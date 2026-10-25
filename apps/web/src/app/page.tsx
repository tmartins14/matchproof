import { Suspense } from "react";
import { Home } from "@/components/desk/Home";

export default function Page() {
  return (
    <Suspense>
      <Home />
    </Suspense>
  );
}
