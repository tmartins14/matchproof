import type { Copy } from "@/desk/copy";
import { fill } from "@/desk/copy";
import type { BeatView } from "@/desk/model";
import type { Mode } from "@/desk/reviewParams";
import { ClaimItem } from "./ClaimItem";
import { VerdictStamp } from "./VerdictStamp";

interface KeyMomentRowProps {
  copy: Copy;
  mode: Mode;
  row: BeatView;
  headline: string;
  onBeat: (beatId: string) => void;
  onClaim: (beatId: string, claimId: string) => void;
}

export function KeyMomentRow({ copy, mode, row, headline, onBeat, onClaim }: KeyMomentRowProps) {
  const checking = row.verdict === "checking";
  const fan = mode === "fan";
  const removedText =
    row.removed === 0 || checking
      ? undefined
      : mode === "producer"
        ? fill(copy.feedExtra.producerRemoved, { n: row.removed })
        : row.removed === 1
          ? copy.feed.removedOne
          : fill(copy.feed.removedMany, { n: row.removed });
  return (
    <li className="mp-moment-row">
      <div className={checking ? undefined : "mp-lift"}>
        <button type="button" className="mp-bar-head" data-checking={checking} aria-expanded={row.selected} onClick={() => onBeat(row.beat.id)}>
          <span className="mp-minute num">{row.beat.label}</span>
          <span className="mp-headline">{headline}</span>
          <span className="mp-bar-stamp">
            <VerdictStamp verdict={row.verdict} copy={copy} />
          </span>
        </button>
      </div>
      {row.selected ? (
        <div className="mp-claims">
          {fan ? (
            <p style={{ fontSize: 17, lineHeight: 1.5 }}>
              {checking ? copy.feed.fanChecking : row.claims.map((c) => c.claim.text).join(" ")}
            </p>
          ) : (
            <ul style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {row.claims.map((view) => (
                <ClaimItem key={view.claim.id} copy={copy} view={view} onPick={(id) => onClaim(row.beat.id, id)} />
              ))}
            </ul>
          )}
          {removedText ? <p className="mp-muted" style={{ fontSize: 13 }}>{removedText}</p> : null}
        </div>
      ) : null}
    </li>
  );
}
