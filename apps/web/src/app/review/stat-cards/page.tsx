import { StatCard } from "@/components/desk/StatCard";
import { copy, type Lang } from "@/desk/copy";
import type { Fact } from "@/contracts/types";
import families from "../../../../fixtures/metric-families.json";
import { statCardView } from "@/desk/railModel";

interface PageProps {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}

/** Review aid: the stat card for one real fact of every metric family the registry emits. */
export default async function StatCards({ searchParams }: PageProps) {
  const lang: Lang = (await searchParams).lang === "es" ? "es" : "en";
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
