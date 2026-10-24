import type { Copy } from "@/desk/copy";
import type { RailEvent } from "@/desk/railModel";
import { SectionTab } from "./SectionTab";

interface TickerPanelProps {
  copy: Copy;
  rows: RailEvent[];
}

export function TickerPanel({ copy, rows }: TickerPanelProps) {
  return (
    <div className="mp-panel" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <SectionTab as="h2" size="sm">
        {copy.ticker.title}
      </SectionTab>
      {rows.length === 0 ? <span className="mp-muted">{copy.ticker.empty}</span> : null}
      <ol className="mp-ticker" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {[...rows].reverse().map((row) => (
          <li key={row.id}>
            <span className="num mp-muted">{row.time}</span>
            <span>
              <span style={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", marginRight: 6, background: row.side === "away" ? "var(--mp-away)" : "var(--mp-home)" }} />
              {row.label}, {row.who}
            </span>
            <span className="mono mp-muted" style={{ fontSize: 12, textAlign: "right" }}>
              {row.id}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}
