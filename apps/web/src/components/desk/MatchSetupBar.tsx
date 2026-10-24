import type { Copy } from "@/desk/copy";
import type { Tactics } from "@/desk/tactics";
import { SectionTab } from "./SectionTab";
import { TacticsFields } from "./TacticsFields";

interface MatchSetupBarProps {
  copy: Copy;
  summary: string;
  brief: string;
  note: string | undefined;
  tactics: Tactics;
  homeName: string;
  awayName: string;
  storylineId: string;
  open: boolean;
  onToggle: () => void;
  onBrief: (text: string) => void;
  onTactics: (next: Tactics) => void;
}

export function MatchSetupBar(props: MatchSetupBarProps) {
  const { copy, summary, brief, note, tactics, open } = props;
  const s = copy.setup;
  const storylineText = s.storylines[props.storylineId as keyof typeof s.storylines] ?? s.storylines.custom;
  return (
    <section className="mp-setup mp-above" aria-label={s.label}>
      <div className="mp-setup-row">
        <SectionTab as="span" size="sm">
          {s.label}
        </SectionTab>
        <p className="mp-setup-summary" title={summary}>
          {summary}
        </p>
        <div className="mp-btns">
          <button type="button" className="mp-btn" aria-expanded={open} aria-controls="mp-setup-body" onClick={props.onToggle}>
            {open ? s.hide : s.edit}
            <svg className="mp-chevron-icon" data-open={open} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M6 9l6 6 6-6" />
            </svg>
          </button>
          <button type="button" className="mp-btn">{s.randomize}</button>
          <button type="button" className="mp-btn mp-btn--primary">{s.kickoff}</button>
          <button type="button" className="mp-btn">{s.cached}</button>
        </div>
      </div>
      {note ? (
        <p role="status" className="mp-note">
          {note}
        </p>
      ) : null}
      {open ? (
        <div id="mp-setup-body" className="mp-setup-body">
          <div className="mp-field" style={{ flex: "999 1 420px", minWidth: 0 }}>
            <label htmlFor="mp-brief" style={{ fontWeight: 600 }}>
              {s.briefLabel}
            </label>
            <textarea id="mp-brief" className="mp-input" rows={3} value={brief} onChange={(e) => props.onBrief(e.target.value)} />
            <div className="mp-btns">
              <button type="button" className="mp-btn">{s.readBrief}</button>
            </div>
          </div>
          <fieldset style={{ flex: "1 1 380px", minWidth: 0, margin: 0, padding: 0, border: 0, display: "flex", flexDirection: "column", gap: 12 }}>
            <legend style={{ padding: 0, marginBottom: 6, fontWeight: 600 }}>{s.tactics}</legend>
            <TacticsFields copy={copy} idPrefix="mp-home" name={props.homeName} home tactics={tactics.home} onChange={(next) => props.onTactics({ ...tactics, home: next })} />
            <TacticsFields copy={copy} idPrefix="mp-away" name={props.awayName} home={false} tactics={tactics.away} onChange={(next) => props.onTactics({ ...tactics, away: next })} />
            <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "8px 12px" }}>
              <label htmlFor="mp-story" className="mp-muted" style={{ fontSize: 13 }}>
                {s.storyline}
              </label>
              <select id="mp-story" className="mp-select" style={{ flex: "1 1 220px", minWidth: 0 }} value={props.storylineId} disabled>
                <option value={props.storylineId}>{storylineText}</option>
              </select>
            </div>
          </fieldset>
        </div>
      ) : null}
    </section>
  );
}
