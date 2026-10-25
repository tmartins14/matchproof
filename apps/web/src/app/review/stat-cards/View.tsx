"use client";

import { useSearchParams } from "next/navigation";
import { StatCard } from "@/components/desk/StatCard";
import { copy, type Lang } from "@/desk/copy";
import type { Fact } from "@/contracts/types";
import families from "../../../../fixtures/metric-families.json";
import { statCardView } from "@/desk/railModel";

export function StatCardsView() {
  const lang: Lang = useSearchParams().get("lang") === "es" ? "es" : "en";
  const rail = { width: 380, margin: "16px auto", display: "flex", flexDirection: "column", gap: 12 } as const;
  return (
    <main className="mp-root" style={{ padding: 16 }}>
      <div className="mp-rail" style={rail}>
        {(families as unknown as Fact[]).map((fact) => (
          <div key={fact.id} data-family={fact.name} className="mp-review-card">
            <StatCard view={statCardView(fact, lang, copy[lang], fact.scope?.side)} />
          </div>
        ))}
      </div>
    </main>
  );
}
