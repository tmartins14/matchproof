import type { Copy } from "@/desk/copy";
import { fill } from "@/desk/copy";
import type { BeatView } from "@/desk/model";
import type { Mode } from "@/desk/reviewParams";
import { ClaimItem } from "./ClaimItem";
import { VerdictStamp } from "./VerdictStamp";

/** A label longer than this many characters takes the smaller type so the minute block never grows. */
export const LONG_LABEL = 6;

/** A headline whose longest unbreakable word has at least this many characters takes the smaller type. */
export const TIGHT_WORD = 9;

/** From the characters alone, never from a measurement: words break at spaces and after hyphens. */
export function needsTightHeadline(headline: string): boolean {
  return headline.split(/\s+|(?<=-)/).some((word) => word.length >= TIGHT_WORD);
}

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
    row.removed === 0 || checking || mode === "analyst"
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
          <span className={row.beat.label.length > LONG_LABEL ? "mp-minute mp-minute--long num" : "mp-minute num"}>{row.beat.label}</span>
          <span className={needsTightHeadline(headline) ? "mp-headline mp-headline--tight" : "mp-headline"}>{headline}</span>
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
