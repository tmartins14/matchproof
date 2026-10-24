import type { StatsView } from "@/desk/statsModel";

interface StatsPanelProps {
  view: StatsView | undefined;
}

export function StatsPanel({ view }: StatsPanelProps) {
  if (!view) return null;
  return (
    <div className="mp-panel" style={{ gap: 10, display: "flex", flexDirection: "column" }}>
      <span className="mp-muted num" style={{ fontSize: 13 }}>
        {view.window}
      </span>
      {view.rows.map((row) => (
        <div className="mp-stat-row" key={row.label} data-facts={row.factIds.join(" ")}>
          <div className="mp-stat-head num">
            <b style={{ color: "var(--mp-homeText)" }}>{row.home}</b>
            <span style={{ textAlign: "center", color: "var(--mp-text2)", fontSize: 14 }}>{row.label}</span>
            <b style={{ color: "var(--mp-awayText)", textAlign: "right" }}>{row.away}</b>
          </div>
          <div className="mp-bar" aria-hidden="true">
            <span style={{ flex: `${row.homeShare} 1 0`, background: "var(--mp-home)" }} />
            <span style={{ flex: `${row.awayShare} 1 0`, background: "var(--mp-away)" }} />
          </div>
        </div>
      ))}
    </div>
  );
}
