import type { Copy } from "@/desk/copy";
import type { ClaimView } from "@/desk/model";
import type { RailView } from "@/desk/railModel";
import { displayReason } from "@/desk/reason";
import { OverturnedLines } from "./OverturnedLines";
import { SectionTab } from "./SectionTab";
import { StatCard } from "./StatCard";
import { VerdictStamp } from "./VerdictStamp";

interface EvidenceRailProps {
  copy: Copy;
  claim: ClaimView | undefined;
  rail: RailView | undefined;
}

export function EvidenceRail({ copy, claim, rail }: EvidenceRailProps) {
  const r = copy.rail;
  const verdict = claim?.verdict;
  const note = verdict === "checking" || verdict === "verified" || verdict === "delayed" ? copy.verdictNote[verdict] : claim?.claim.reason ? displayReason(claim.claim.reason, copy) : undefined;
  return (
    <aside className="mp-col-rail mp-above" aria-label={r.title}>
      <div className="mp-rail">
        <div className="mp-rail-head">
          <SectionTab size="md">{r.title}</SectionTab>
          <span className="mono mp-muted mp-rail-id" title={claim?.claim.id}>{claim?.claim.id}</span>
        </div>
        {!claim || !rail ? <p className="mp-muted">{r.empty}</p> : null}
        {claim && rail ? (
          <>
            {rail.statCard ? <StatCard view={rail.statCard} /> : null}
            <div className="mp-step">
              <span>{r.claim}</span>
              {verdict === "blocked" ? (
                <OverturnedLines claim={claim.claim} copy={copy} display />
              ) : (
                <span className="display" style={{ fontSize: 22, fontWeight: 600, lineHeight: 1.25 }}>
                  {claim.claim.text}
                </span>
              )}
            </div>
            <div className="mp-step">
              <span>{r.fact}</span>
              <code className="mp-code">{rail.factLines.join("\n")}</code>
            </div>
            <div className="mp-step">
              <span>{r.events}</span>
              {rail.events.length === 0 ? <span style={{ color: "var(--mp-overturned)", fontSize: 14 }}>{r.noEvents}</span> : null}
              <div className="mp-events">
                {rail.events.map((e) => (
                  <div key={e.id}>
                    <span className="mono">{e.id}</span>
                    <span>
                      {e.label}
                      {e.who ? `, ${e.who}` : ""}
                    </span>
                    <span className="num mp-muted" style={{ textAlign: "right" }}>{e.time}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="mp-step" style={{ alignItems: "flex-start" }}>
              <span>{r.verdict}</span>
              {verdict ? <VerdictStamp verdict={verdict} copy={copy} /> : null}
              {note ? <span className="mp-note">{note}</span> : null}
            </div>
          </>
        ) : null}
      </div>
    </aside>
  );
}
