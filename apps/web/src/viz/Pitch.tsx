import type { Copy } from "@/desk/copy";
import { fill } from "@/desk/copy";
import { formatClock } from "@/desk/format";
import type { PitchMark, PitchView } from "@/desk/pitchModel";
import { PitchMarkings } from "./PitchMarkings";

interface PitchProps {
  copy: Copy;
  view: PitchView;
  headline: string;
  checking: boolean;
}

function captionText(copy: Copy, caption: PitchView["caption"]): string | undefined {
  switch (caption?.kind) {
    case "freeze":
      return fill(copy.pitch.freeze, { clock: formatClock(caption.t) });
    case "focus":
      return copy.pitch.focus;
    case "live":
      return copy.pitch.livePlay;
    case "start":
      return copy.pitch.startingShape;
    default:
      return undefined;
  }
}

const pct = (value: number, of: number): string => `${((value / of) * 100).toFixed(2)}%`;
const side = (s: "home" | "away"): string => (s === "home" ? "var(--mp-home)" : "var(--mp-away)");

function MarkLines({ marks }: { marks: PitchMark[] }) {
  return (
    <svg viewBox="0 0 120 80" preserveAspectRatio="none" aria-hidden="true">
      {marks
        .filter((m) => m.to && (m.kind === "pass" || m.kind === "carry" || m.kind === "shot"))
        .map((m) => (
          <line
            key={m.id}
            x1={m.at[0]}
            y1={m.at[1]}
            x2={m.to?.[0]}
            y2={m.to?.[1]}
            stroke={side(m.side)}
            strokeWidth={m.kind === "shot" ? 3 : 2}
            strokeDasharray={m.kind === "carry" ? "5 4" : undefined}
            opacity={m.dim ? 0.18 : 1}
            vectorEffect="non-scaling-stroke"
          />
        ))}
    </svg>
  );
}

function MarkDot({ mark }: { mark: PitchMark }) {
  const base = { position: "absolute", left: pct(mark.at[0], 120), top: pct(mark.at[1], 80), opacity: mark.dim ? 0.18 : 1, boxSizing: "border-box" } as const;
  if (mark.kind === "pressure") {
    return <div style={{ ...base, width: 20, height: 20, borderRadius: "50%", border: `2px solid ${side(mark.side)}`, transform: "translate(-50%,-50%)" }} />;
  }
  if (mark.kind === "turnover") {
    return <div style={{ ...base, width: 12, height: 12, background: side(mark.side), transform: "translate(-50%,-50%) rotate(45deg)" }} />;
  }
  if (mark.kind === "shot") {
    const d = Math.round(10 + (mark.xg ?? 0) * 44);
    return (
      <div
        style={{ ...base, width: d, height: d, borderRadius: "50%", background: side(mark.side), border: "1.5px solid var(--mp-text)", transform: "translate(-50%,-50%)", boxShadow: mark.goal ? "0 0 0 3px var(--mp-pitch), 0 0 0 5px var(--mp-lime)" : undefined }}
      />
    );
  }
  return null;
}

export function Pitch({ copy, view, headline, checking }: PitchProps) {
  const { frame, marks, highlight } = view;
  const caption = captionText(copy, view.caption);
  const lit = checking ? new Set(highlight?.player_ids ?? []) : new Set<string>();
  return (
    <div className="mp-pitch" role="img" aria-label={fill(copy.pitch.aria, { headline, n: frame?.players.length ?? 0 })}>
      <PitchMarkings />
      {checking && highlight?.zone ? (
        <div className="mp-zone" style={{ left: pct(highlight.zone.x_from, 120), width: pct(highlight.zone.x_to - highlight.zone.x_from, 120) }} />
      ) : null}
      {frame?.players.map((p) => (
        <div
          key={p.id}
          className={`mp-dot mp-dot--${p.side}${view.goalkeepers.has(p.id) ? " mp-dot--gk" : ""}${lit.has(p.id) ? " mp-dot--lit" : ""}`}
          style={{ left: pct(p.at[0], 120), top: pct(p.at[1], 80), opacity: 0.45 }}
        />
      ))}
      <MarkLines marks={marks} />
      {marks.map((m) => (
        <MarkDot key={m.id} mark={m} />
      ))}
      {frame ? <div className="mp-ball" style={{ left: pct(frame.ball[0], 120), top: pct(frame.ball[1], 80) }} /> : null}
      {caption ? (
        <div className="mp-lift" style={{ position: "absolute", left: "50%", bottom: 18, transform: "translateX(-50%)" }}>
          <span className="mp-caption mp-cut" style={{ position: "static", transform: "none", display: "block" }}>
            {caption}
          </span>
        </div>
      ) : null}
      <span className="mp-attack">{copy.pitch.attack}</span>
    </div>
  );
}
