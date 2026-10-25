"use client";

import { useLayoutEffect, useRef, useState } from "react";
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

const LABEL_GAP_PX = 6;

/** Which pin labels to hide: the selected one always shows, then the rest left to right, each only if it clears the labels already kept. */
function overlapping(labels: Map<string, HTMLElement>, selected: string | undefined): Set<string> {
  const rects = [...labels].map(([id, el]) => ({ id, rect: el.getBoundingClientRect() }));
  rects.sort((a, b) => (a.id === selected ? -1 : b.id === selected ? 1 : a.rect.left - b.rect.left));
  const kept: DOMRect[] = [];
  const hidden = new Set<string>();
  for (const { id, rect } of rects) {
    if (kept.some((k) => rect.left < k.right + LABEL_GAP_PX && k.left < rect.right + LABEL_GAP_PX)) hidden.add(id);
    else kept.push(rect);
  }
  return hidden;
}

/** Diverging bars, one per closed 5-minute bucket. Heights are the facts' values over the largest so far. */
export function MomentumStrip({ copy, bars, model, gridSeconds, headlineOf, onPick }: MomentumStripProps) {
  const wrap = useRef<HTMLDivElement>(null);
  const labels = useRef(new Map<string, HTMLElement>());
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const selectedId = model.selectedBeat?.id;
  const pinKey = model.revealed.map((b) => b.id).join(" ");

  useLayoutEffect(() => {
    const measure = (): void => {
      const next = overlapping(labels.current, selectedId);
      setHidden((prev) => (prev.size === next.size && [...next].every((id) => prev.has(id)) ? prev : next));
    };
    measure();
    const observer = new ResizeObserver(measure);
    if (wrap.current) observer.observe(wrap.current);
    return () => observer.disconnect();
  }, [selectedId, pinKey]);

  return (
    <div className="mp-panel" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <SectionTab as="h2" size="sm">
        {copy.momentum.title}
      </SectionTab>
      <div className="mp-moment-wrap" ref={wrap}>
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
        </div>
        <div className="num mp-muted mp-moment-ticks">
          <span>0′</span>
          <span>45′</span>
          <span>90′</span>
        </div>
        <div className="mp-pin-row" />
        {model.revealed.map((beat) => {
          const left = Math.min((beat.t_detect / gridSeconds) * 100, 100);
          const selected = beat.id === selectedId;
          return (
            <button
              key={beat.id}
              type="button"
              className="mp-pin"
              data-edge={left > 92 ? "end" : left < 8 ? "start" : "mid"}
              aria-pressed={selected}
              aria-label={fill(copy.momentum.pin, { headline: headlineOf(beat.kind), label: beat.label })}
              style={{ left: `${left}%` }}
              onClick={() => onPick(beat.id)}
            >
              <span className="mp-pin-tick" />
              <span
                className="mp-pin-label"
                data-hidden={!selected && hidden.has(beat.id)}
                ref={(el) => {
                  if (el) labels.current.set(beat.id, el);
                  else labels.current.delete(beat.id);
                }}
              >
                {beat.label}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
