import type { Copy } from "@/desk/copy";
import type { DeskModel } from "@/desk/model";
import type { Mode } from "@/desk/reviewParams";
import { KeyMomentRow } from "./KeyMomentRow";
import { SectionTab } from "./SectionTab";

interface KeyMomentFeedProps {
  copy: Copy;
  mode: Mode;
  model: DeskModel;
  headlineOf: (kind: string) => string;
  onBeat: (beatId: string) => void;
  onClaim: (beatId: string, claimId: string) => void;
  /** `NARRATOR · <MODEL>` on every claim item (the Trials desk) */
  badge?: string;
  /** The Compare page for a beat, when the match is a pack fixture */
  compareHref?: (beatId: string) => string | undefined;
}

export function KeyMomentFeed({ copy, mode, model, headlineOf, onBeat, onClaim, badge, compareHref }: KeyMomentFeedProps) {
  return (
    <section className="mp-col-feed mp-above" aria-label={copy.feed.title}>
      <SectionTab size="md">{copy.feed.title}</SectionTab>
      {model.feed.length === 0 ? <p className="mp-muted">{copy.feed.empty}</p> : null}
      <ol style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {model.feed.map((row) => (
          <KeyMomentRow key={row.beat.id} copy={copy} mode={mode} row={row} headline={headlineOf(row.beat.kind)} onBeat={onBeat} onClaim={onClaim} badge={badge} compareHref={compareHref?.(row.beat.id)} />
        ))}
      </ol>
    </section>
  );
}
