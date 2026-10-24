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
          {view.window ? <span className="num">{view.window}</span> : null}
          <span className="mono mp-card-id" title={view.factId}>
            {view.factId}
          </span>
        </span>
      </div>
    </div>
  );
}
