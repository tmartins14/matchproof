import type { Copy } from "@/desk/copy";
import { fill } from "@/desk/copy";
import type { DeskModel } from "@/desk/model";
import type { MomentumBar } from "@/desk/statsModel";
import { SectionTab } from "./SectionTab";

interface MomentumStripProps {
  copy: Copy;
  bars: MomentumBar[];
  model: DeskModel;
  matchSeconds: number;
  headlineOf: (kind: string) => string;
  onPick: (beatId: string) => void;
}

export function MomentumStrip({ copy, bars, model, matchSeconds, headlineOf, onPick }: MomentumStripProps) {
  return (
    <div className="mp-panel" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <SectionTab as="h2" size="sm">
        {copy.momentum.title}
      </SectionTab>
      <div className="mp-moment" aria-hidden="true">
        {bars.map((bar) => (
          <div className="mp-moment-col" key={bar.id}>
            <div style={{ position: "absolute", left: 0, right: 0, bottom: "50%", height: `${bar.home * 50}%`, background: "var(--mp-home)" }} />
            <div style={{ position: "absolute", left: 0, right: 0, top: "50%", height: `${bar.away * 50}%`, background: "var(--mp-away)" }} />
          </div>
        ))}
      </div>
      <div className="mp-pins">
        {model.revealed.map((beat) => {
          const left = (beat.t_detect / matchSeconds) * 100;
          return (
            <button
              key={beat.id}
              type="button"
              className="mp-pin"
              aria-pressed={beat.id === model.selectedBeat?.id}
              aria-label={fill(copy.momentum.pin, { headline: headlineOf(beat.kind), label: beat.label })}
              style={{ left: `${left}%`, transform: `translateX(${left > 85 ? "-88%" : "-50%"})` }}
              onClick={() => onPick(beat.id)}
            >
              {beat.label}
            </button>
          );
        })}
      </div>
      <div className="num mp-muted" style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
        <span>0′</span>
        <span>45′</span>
        <span>90′</span>
      </div>
    </div>
  );
}
