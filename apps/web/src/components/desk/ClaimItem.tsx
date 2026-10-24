import type { Copy } from "@/desk/copy";
import type { ClaimView } from "@/desk/model";
import { VerdictStamp } from "./VerdictStamp";

interface ClaimItemProps {
  copy: Copy;
  view: ClaimView;
  onPick: (claimId: string) => void;
}

export function ClaimItem({ copy, view, onPick }: ClaimItemProps) {
  const { claim, verdict, selected } = view;
  const amended = verdict === "rephrased" && claim.draft_text;
  const overturned = verdict === "blocked";
  return (
    <li>
      <button type="button" className="mp-claim" aria-pressed={selected} onClick={() => onPick(claim.id)}>
        {amended ? <span className="mp-struck" style={{ fontSize: 14 }}>{claim.draft_text}</span> : null}
        <span className={overturned ? "mp-struck" : undefined} style={{ fontWeight: 500, lineHeight: 1.35 }}>
          {overturned ? (claim.draft_text ?? claim.text) : claim.text}
        </span>
        {overturned && claim.reason ? <span className="mp-note">{claim.reason}</span> : null}
        <span style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: "6px 10px" }}>
          <span className="mono mp-muted" style={{ fontSize: 12 }}>
            {claim.fact_ids[0]}
          </span>
          <VerdictStamp verdict={verdict} copy={copy} reason={claim.reason} />
        </span>
      </button>
    </li>
  );
}
