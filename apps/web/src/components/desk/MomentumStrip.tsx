import type { Copy } from "@/desk/copy";
import { fill } from "@/desk/copy";
import type { DeskModel } from "@/desk/model";
import { MOMENTUM_SLOTS, type MomentumBar } from "@/desk/statsModel";
import { SectionTab } from "./SectionTab";

interface MomentumStripProps {
  copy: Copy;
  bars: MomentumBar[];
  model: DeskModel;
  /** seconds the strip spans: 0′ at the left edge, 90′ at the right */
  gridSeconds: number;
  headlineOf: (kind: string) => string;
  onPick: (beatId: string) => void;
}

/** Diverging bars, one per closed 5-minute bucket. Heights are the facts' values over the largest so far. */
export function MomentumStrip({ copy, bars, model, gridSeconds, headlineOf, onPick }: MomentumStripProps) {
  return (
    <div className="mp-panel" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <SectionTab as="h2" size="sm">
        {copy.momentum.title}
      </SectionTab>
      <div className="mp-moment">
        <div className="mp-moment-bars" aria-hidden="true" style={{ gridTemplateColumns: `repeat(${MOMENTUM_SLOTS}, minmax(0, 1fr))` }}>
          {bars.map((bar) => (
            <div className="mp-moment-col" key={bar.factId} data-fact={bar.factId} data-slot={bar.slot} style={{ gridColumn: bar.slot + 1 }}>
              {bar.value === 0 ? (
                <div className="mp-moment-zero" />
              ) : (
                <div
                  className="mp-moment-bar"
                  data-side={bar.value > 0 ? "home" : "away"}
                  style={bar.value > 0 ? { bottom: "50%", height: `${bar.scale * 50}%`, background: "var(--mp-home)" } : { top: "50%", height: `${-bar.scale * 50}%`, background: "var(--mp-away)" }}
                />
              )}
            </div>
          ))}
        </div>
        {model.revealed.map((beat) => {
          const left = Math.min((beat.t_detect / gridSeconds) * 100, 100);
          const selected = beat.id === model.selectedBeat?.id;
          return (
            <button
              key={beat.id}
              type="button"
              className="mp-pin"
              data-edge={left > 80 ? "end" : "mid"}
              aria-pressed={selected}
              aria-label={fill(copy.momentum.pin, { headline: headlineOf(beat.kind), label: beat.label })}
              style={{ left: `${left}%` }}
              onClick={() => onPick(beat.id)}
            >
              <span className="mp-pin-chip">
                <span className="mp-pin-text">{beat.label}</span>
              </span>
            </button>
          );
        })}
      </div>
      <div className="num mp-muted mp-moment-ticks">
        <span>0′</span>
        <span>45′</span>
        <span>90′</span>
      </div>
    </div>
  );
}
