import Link from "next/link";
import type { Copy } from "@/desk/copy";
import type { ClaimView } from "@/desk/model";
import { displayReason, reasonLines } from "@/desk/reason";
import { OverturnedLines } from "./OverturnedLines";
import { VerdictStamp } from "./VerdictStamp";

interface ClaimItemProps {
  copy: Copy;
  view: ClaimView;
  onPick: (claimId: string) => void;
  /** `NARRATOR · <MODEL>` */
  badge?: string;
  /** Where the other narrators called this moment; offered on an amended or overturned claim */
  compareHref?: string;
}

export function ClaimItem({ copy, view, onPick, badge, compareHref }: ClaimItemProps) {
  const { claim, verdict, selected } = view;
  const amended = verdict === "rephrased" && claim.draft_text;
  const overturned = verdict === "blocked";
  return (
    <li>
      <button type="button" className="mp-claim" aria-pressed={selected} onClick={() => onPick(claim.id)}>
        {amended ? <span className="mp-struck" style={{ fontSize: 14 }}>{claim.draft_text}</span> : null}
        {overturned ? (
          <OverturnedLines claim={claim} copy={copy} />
        ) : (
          <span style={{ fontWeight: 500, lineHeight: 1.35 }}>{claim.text}</span>
        )}
        {overturned && claim.reason ? (
          <span className="mp-note">
            {reasonLines(claim.reason, copy).map((line) => (
              <span key={line} style={{ display: "block" }}>
                {line}
              </span>
            ))}
          </span>
        ) : null}
        {badge ? <span className="tr-badge">{badge}</span> : null}
        <span style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: "6px 10px" }}>
          <span className="mono mp-muted" style={{ fontSize: 12 }}>
            {claim.fact_ids[0]}
          </span>
          <VerdictStamp verdict={verdict} copy={copy} reason={claim.reason ? displayReason(claim.reason, copy) : undefined} />
        </span>
      </button>
      {compareHref && (verdict === "blocked" || verdict === "rephrased") ? (
        <Link href={compareHref} className="tr-link tr-claim-compare">
          {copy.trials.desk.seeOthers}
        </Link>
      ) : null}
    </li>
  );
}
