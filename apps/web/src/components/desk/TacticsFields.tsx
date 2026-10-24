import type { Copy } from "@/desk/copy";
import { dialWord, formations, type Formation, type SideTactics } from "@/desk/tactics";

interface TacticsFieldsProps {
  copy: Copy;
  idPrefix: string;
  name: string;
  home: boolean;
  tactics: SideTactics;
  onChange: (next: SideTactics) => void;
}

export function TacticsFields({ copy, idPrefix, name, home, tactics, onChange }: TacticsFieldsProps) {
  const names = home ? copy.setup.dials : copy.setup.dialsAway;
  return (
    <div className="mp-field" style={{ gap: 6 }}>
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "8px 12px" }}>
        <span style={{ fontWeight: 600, minWidth: 100, color: home ? "var(--mp-homeText)" : "var(--mp-awayText)" }}>{name}</span>
        <label htmlFor={`${idPrefix}-form`} className="mp-muted" style={{ fontSize: 13 }}>
          {copy.setup.formation}
        </label>
        <select
          id={`${idPrefix}-form`}
          className="mp-select"
          value={tactics.formation}
          onChange={(e) => onChange({ ...tactics, formation: e.target.value as Formation })}
        >
          {formations.map((f) => (
            <option key={f} value={f}>
              {f}
            </option>
          ))}
        </select>
      </div>
      {names.map((dialName, k) => (
        <div className="mp-dial" key={dialName}>
          <label htmlFor={`${idPrefix}-${k}`} className="mp-muted">
            {dialName}
          </label>
          <input
            id={`${idPrefix}-${k}`}
            type="range"
            min={0}
            max={1}
            step={0.01}
            value={tactics.dials[k] ?? 0}
            style={{ accentColor: home ? "var(--mp-home)" : "var(--mp-away)" }}
            onChange={(e) => {
              const dials = [...tactics.dials] as SideTactics["dials"];
              dials[k] = Number(e.target.value);
              onChange({ ...tactics, dials });
            }}
          />
          <span style={{ textAlign: "right" }}>{dialWord(copy, k, tactics.dials[k] ?? 0)}</span>
        </div>
      ))}
    </div>
  );
}
