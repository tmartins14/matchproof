import type { Copy } from "@/desk/copy";

export function PitchLegend({ copy }: { copy: Copy }) {
  const l = copy.pitch.legend;
  const swatch = { display: "inline-block", boxSizing: "border-box", background: "var(--mp-muted)" } as const;
  return (
    <div className="mp-legend" aria-hidden="true">
      <span><i style={{ ...swatch, width: 12, height: 12, borderRadius: "50%", background: "transparent", border: "2px solid var(--mp-muted)" }} />{l.pressure}</span>
      <span><i style={{ ...swatch, width: 9, height: 9, transform: "rotate(45deg)" }} />{l.won}</span>
      <span><i style={{ ...swatch, width: 18, height: 2 }} />{l.pass}</span>
      <span><i style={{ ...swatch, width: 18, height: 0, background: "transparent", borderTop: "2px dashed var(--mp-muted)" }} />{l.carry}</span>
      <span><i style={{ ...swatch, width: 10, height: 10, borderRadius: "50%" }} />{l.shot}</span>
      <span><i style={{ ...swatch, width: 10, height: 10, borderRadius: "50%", opacity: 0.6 }} />{l.player}</span>
      <span><i style={{ ...swatch, width: 10, height: 10, opacity: 0.6 }} />{l.goalkeeper}</span>
    </div>
  );
}
