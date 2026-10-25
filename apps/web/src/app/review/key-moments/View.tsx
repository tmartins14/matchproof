"use client";

import { KeyMomentRow } from "@/components/desk/KeyMomentRow";
import { copy, type Lang } from "@/desk/copy";
import type { Beat } from "@/contracts/types";
import type { BeatView, Verdict } from "@/desk/model";

const VERDICTS: Verdict[] = ["checking", "verified", "rephrased", "blocked", "delayed"];

/** Every headline in the copy file beside every stamp, in the desk's own three-column layout. */
export function KeyMomentsView({ lang }: { lang: Lang }) {
  const c = copy[lang];
  const rows = Object.entries(c.beatKind).flatMap(([kind, headline]) =>
    VERDICTS.map((verdict): { key: string; headline: string; row: BeatView } => ({
      key: `${kind}-${verdict}`,
      headline,
      row: {
        beat: { id: `bt-${kind}-${verdict}`, kind, label: "90+4′" } as unknown as Beat,
        headlineKey: kind,
        verdict,
        claims: [],
        removed: 0,
        verdicts: [verdict],
        selected: false,
      },
    })),
  );
  return (
    <main className="mp-root">
      <div className="mp-main mp-above">
        <section className="mp-col-match" aria-hidden="true" />
        <section className="mp-col-feed">
          <ol style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {rows.map(({ key, headline, row }) => (
              <KeyMomentRow key={key} copy={c} mode="analyst" row={row} headline={headline} onBeat={() => undefined} onClaim={() => undefined} />
            ))}
          </ol>
        </section>
        <aside className="mp-col-rail" aria-hidden="true" />
      </div>
    </main>
  );
}
