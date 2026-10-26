import { copy, fill } from "@/desk/copy";
import { failParts } from "@/trials/format";

/** One stacked bar of the fail profile. Each bucket has its own fill and a text label, so colour is never the only cue. */
export function FailBar({ profile, measured = true }: { profile: Record<string, number>; measured?: boolean }) {
  const t = copy.en.trials;
  const parts = failParts(profile);
  if (parts.length === 0) return <span className="tr-mono tr-dim">{measured ? t.table.noFails : "n/a"}</span>;
  const label = (b: string): string => t.buckets[b as keyof typeof t.buckets] ?? b;
  const text = parts.map((p) => `${label(p.bucket)} ${Math.round(p.share * 100)}%`).join(", ");
  return (
    <div className="tr-fail" tabIndex={0} role="img" aria-label={fill(t.table.failAria, { parts: text })}>
      <div className="tr-fail-bar" aria-hidden="true">
        {parts.map((p) => (
          <span key={p.bucket} className={`tr-fail-seg tr-bucket--${p.bucket}`} style={{ flexGrow: p.share }} />
        ))}
      </div>
      <div className="tr-fail-legend" aria-hidden="true">
        {parts.map((p) => (
          <span key={p.bucket} className="tr-fail-key">
            <i className={`tr-fail-swatch tr-bucket--${p.bucket}`} /> {label(p.bucket)} {Math.round(p.share * 100)}%
          </span>
        ))}
      </div>
    </div>
  );
}
