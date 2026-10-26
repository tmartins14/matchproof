import type { Copy } from "@/desk/copy";
import { fill } from "@/desk/copy";
import type { PipelineView } from "@/desk/statsModel";
import { signedPts, type RecordView } from "@/trials/record";

interface PipelineStripProps {
  copy: Copy;
  view: PipelineView;
  running: boolean;
  /** The Trials desk's RECORD tile; it takes the place of the Events tile. */
  record?: { view: RecordView; title: string };
}

export function PipelineStrip({ copy, view, running, record }: PipelineStripProps) {
  const p = copy.pipeline;
  const number = new Intl.NumberFormat("en-US");
  const checker =
    fill(p.checkerSummary, { stand: view.stand, amended: view.amended, overturned: view.overturned }) +
    (view.checking > 0 ? `, ${fill(p.checkerChecking, { n: view.checking })}` : "");
  const stages = [
    record
      ? { name: record.title, value: signedPts(record.view.pts), detail: `${fill(copy.trials.desk.recordLine, { stands: record.view.STANDS, amended: record.view.AMENDED, overturned: record.view.OVERTURNED, checking: record.view.CHECKING })} · ${fill(copy.trials.desk.recordPts, { pts: signedPts(record.view.pts) })}`, active: record.view.CHECKING > 0, record: true }
      : { name: p.events, value: number.format(view.events), detail: p.eventsDetail, active: running, record: false },
    { name: p.facts, value: number.format(view.facts), detail: p.factsDetail, active: running, record: false },
    { name: p.beats, value: String(view.beats), detail: p.beatsDetail, active: running, record: false },
    { name: p.claims, value: String(view.claims), detail: p.claimsDetail, active: view.checking > 0, record: false },
    { name: p.checker, value: String(view.stand + view.amended + view.overturned), detail: checker, active: view.checking > 0, record: false },
  ];
  return (
    <section className="mp-pipeline mp-above" aria-label={p.label}>
      {stages.map((stage) => (
        <div key={stage.name} className="mp-stage" data-active={stage.active} data-record={stage.record}>
          <span className="mp-muted">{stage.name}</span>
          <b className="num">{stage.value}</b>
          <span style={{ color: "var(--mp-text2)" }}>{stage.detail}</span>
        </div>
      ))}
    </section>
  );
}
