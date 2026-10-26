import type { Copy } from "@/desk/copy";
import type { Tactics } from "@/desk/tactics";
import { SectionTab } from "./SectionTab";
import { SegmentedControl } from "./SegmentedControl";
import { TacticsFields } from "./TacticsFields";

interface MatchSetupBarProps {
  copy: Copy;
  summary: string;
  /** the summary is the first sentence of a brief the user wrote, not the tactics shorthand */
  custom: boolean;
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
  /** Present on the live desk; the fixture's controls do nothing. */
  actions?: SetupActions;
}

export interface SetupActions {
  /** a match is connecting or playing: the brief and the speed are fixed */
  locked: boolean;
  /** the narrator strip owns Kick off and New match */
  inStrip?: boolean;
  /** a cached run plays pack fixtures only: Randomize, Read brief, tactics and speed are off */
  cachedOnly?: boolean;
  /** the match is over or the connection broke: New match is offered */
  finished: boolean;
  reading: boolean;
  warnings: string[];
  speed: 1 | 3 | 6;
  /** the storylines the select offers, with their display text */
  storylines: { id: string; text: string }[];
  onSpeed: (speed: 1 | 3 | 6) => void;
  onStoryline: (id: string) => void;
  onRandomize: () => void;
  onRead: () => void;
  onKickoff: () => void;
  onNewMatch: () => void;
}

interface ButtonProps extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, "className"> {
  primary?: boolean;
}

/** Cut buttons take their offset shadow from the wrapper: box-shadow would be clipped with the button. */
function Button({ primary, children, ...rest }: ButtonProps) {
  return (
    <span className="mp-lift">
      <button type="button" className={primary ? "mp-btn mp-btn--primary" : "mp-btn"} {...rest}>
        {children}
      </button>
    </span>
  );
}

export function MatchSetupBar(props: MatchSetupBarProps) {
  const { copy, summary, custom, brief, note, tactics, open, actions } = props;
  const cachedOnly = actions?.cachedOnly ?? false;
  const locked = (actions?.locked ?? false) || cachedOnly;
  const s = copy.setup;
  const cachedWhy = cachedOnly ? copy.trials.desk.cachedOnly : undefined;
  const storylineText = s.storylines[props.storylineId as keyof typeof s.storylines] ?? s.storylines.custom;
  return (
    <section className="mp-setup mp-above" aria-label={s.label}>
      <div className="mp-setup-row">
        <SectionTab as="span" size="sm">
          {s.label}
        </SectionTab>
        <p className="mp-setup-summary">
          {custom ? <span className="mp-muted">{s.customBrief} </span> : null}
          {summary}
        </p>
        <div className="mp-btns">
          <Button onClick={props.onToggle} aria-expanded={open} aria-controls="mp-setup-body">
            {open ? s.hide : s.edit}
            <svg className="mp-chevron-icon" data-open={open} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M6 9l6 6 6-6" />
            </svg>
          </Button>
          <Button onClick={actions?.onRandomize} disabled={locked} title={cachedWhy}>
            {s.randomize}
          </Button>
          {actions ? (
            <SegmentedControl label={s.speed} value={String(actions.speed) as "1" | "3" | "6"} disabled={locked} onChange={(v) => actions.onSpeed(Number(v) as 1 | 3 | 6)} options={[{ value: "1", label: "1×" }, { value: "3", label: "3×" }, { value: "6", label: "6×" }]} />
          ) : null}
          {cachedOnly ? <span className="tr-sub">{copy.trials.desk.cachedSpeed}</span> : null}
          {actions?.inStrip ? null : actions?.finished ? (
            <Button primary onClick={actions.onNewMatch}>
              {s.newMatch}
            </Button>
          ) : (
            <Button primary onClick={actions?.onKickoff} disabled={locked}>
              <i className="mp-btn-dot" aria-hidden="true" />
              {s.kickoff}
            </Button>
          )}
          {actions?.inStrip ? null : (
            <Button disabled title={s.cachedSoon}>
              {s.cached}
            </Button>
          )}
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
            <textarea id="mp-brief" className="mp-input" rows={3} value={brief} disabled={locked} onChange={(e) => props.onBrief(e.target.value)} />
            <div className="mp-btns">
              <Button onClick={actions?.onRead} disabled={locked || actions?.reading} title={cachedWhy}>
                {actions?.reading ? s.reading : s.readBrief}
              </Button>
            </div>
            {actions?.warnings.map((w) => (
              <p key={w} className="mp-muted" style={{ fontSize: 13 }}>
                {w}
              </p>
            ))}
          </div>
          <fieldset disabled={locked} style={{ flex: "1 1 380px", minWidth: 0, margin: 0, padding: 0, border: 0, display: "flex", flexDirection: "column", gap: 12 }}>
            <legend style={{ padding: 0, marginBottom: 6, fontWeight: 600 }}>{s.tactics}</legend>
            <TacticsFields copy={copy} idPrefix="mp-home" name={props.homeName} home tactics={tactics.home} onChange={(next) => props.onTactics({ ...tactics, home: next })} />
            <TacticsFields copy={copy} idPrefix="mp-away" name={props.awayName} home={false} tactics={tactics.away} onChange={(next) => props.onTactics({ ...tactics, away: next })} />
            <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "8px 12px" }}>
              <label htmlFor="mp-story" className="mp-muted" style={{ fontSize: 13 }}>
                {s.storyline}
              </label>
              <select id="mp-story" className="mp-select" style={{ flex: "1 1 220px", minWidth: 0 }} value={props.storylineId} disabled={!actions || locked} onChange={(e) => actions?.onStoryline(e.target.value)}>
                {actions?.storylines.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.text}
                  </option>
                ))}
                {actions?.storylines.some((o) => o.id === props.storylineId) ? null : <option value={props.storylineId}>{storylineText}</option>}
              </select>
            </div>
          </fieldset>
        </div>
      ) : null}
    </section>
  );
}
