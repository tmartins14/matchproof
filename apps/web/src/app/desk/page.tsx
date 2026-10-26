import { Suspense } from "react";
import { Home } from "@/components/desk/Home";

export const metadata = { title: "Matchproof live desk" };

export default function Page() {
  return (
    <Suspense>
      <Home />
    </Suspense>
  );
}
