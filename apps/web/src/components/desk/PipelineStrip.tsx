import type { Copy } from "@/desk/copy";
import { fill } from "@/desk/copy";
import type { PipelineView } from "@/desk/statsModel";

interface PipelineStripProps {
  copy: Copy;
  view: PipelineView;
  running: boolean;
}

export function PipelineStrip({ copy, view, running }: PipelineStripProps) {
  const p = copy.pipeline;
  const number = new Intl.NumberFormat("en-US");
  const checker =
    fill(p.checkerSummary, { stand: view.stand, amended: view.amended, overturned: view.overturned }) +
    (view.checking > 0 ? `, ${fill(p.checkerChecking, { n: view.checking })}` : "");
  const stages = [
    { name: p.events, value: number.format(view.events), detail: p.eventsDetail, active: running },
    { name: p.facts, value: number.format(view.facts), detail: p.factsDetail, active: running },
    { name: p.beats, value: String(view.beats), detail: p.beatsDetail, active: running },
    { name: p.claims, value: String(view.claims), detail: p.claimsDetail, active: view.checking > 0 },
    { name: p.checker, value: String(view.stand + view.amended + view.overturned), detail: checker, active: view.checking > 0 },
  ];
  return (
    <section className="mp-pipeline mp-above" aria-label={p.label}>
      {stages.map((stage) => (
        <div key={stage.name} className="mp-stage" data-active={stage.active}>
          <span className="mp-muted">{stage.name}</span>
          <b className="num">{stage.value}</b>
          <span style={{ color: "var(--mp-text2)" }}>{stage.detail}</span>
        </div>
      ))}
    </section>
  );
}
