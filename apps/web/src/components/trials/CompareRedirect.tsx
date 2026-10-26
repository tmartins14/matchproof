"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { copy } from "@/desk/copy";
import { firstTrapBeat } from "@/trials/data";
import { Shell } from "./Shell";

/** /compare opens the first trap moment of fx-01. */
export function CompareRedirect() {
  const router = useRouter();
  const target = `/compare/fx-01/${firstTrapBeat("fx-01") ?? ""}`;
  useEffect(() => {
    router.replace(target);
  }, [router, target]);
  return (
    <Shell>
      <p className="tr-body">
        <Link className="tr-link" href={target}>
          {copy.en.trials.compare.redirecting}
        </Link>
      </p>
    </Shell>
  );
}
