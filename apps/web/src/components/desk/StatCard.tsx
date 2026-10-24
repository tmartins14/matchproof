import type { StatCardView } from "@/desk/railModel";

interface StatCardProps {
  view: StatCardView;
}

export function StatCard({ view }: StatCardProps) {
  return (
    <div className="mp-lift">
      <div className="mp-card" data-fact={view.factId}>
        <span className="mp-card-value num">{view.value}</span>
        <span className="mp-card-label">
          <b>{view.metric}</b>
          <span className="mono" style={{ fontSize: 12 }}>
            {view.factId}
            {view.window ? ` · ${view.window}` : ""}
          </span>
        </span>
      </div>
    </div>
  );
}
