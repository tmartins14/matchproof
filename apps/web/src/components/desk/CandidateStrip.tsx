import type { Copy } from "@/desk/copy";
import { fill } from "@/desk/copy";
import { deskCandidates, liveNarrator, rankOf, trapLabels, web } from "@/trials/data";
import { fixtureNumber } from "@/trials/format";

/** What the Desk needs to know about the Trials choice; the strip and the desk both read it. */
export interface TrialsDeskProps {
  narrator: string;
  fixture: string;
  /** the selected narrator is not the live one: its claims replay from the pack run */
  cachedMode: boolean;
  /** the desk is showing a cached replay (selected, or the fallback after live failed) */
  playingCached: boolean;
  /** live kickoff failed with busy, unreachable or rate_limit */
  fallback: boolean;
  onNarrator: (id: string) => void;
  onFixture: (id: string) => void;
  onFallback: () => void;
}

interface StripProps extends TrialsDeskProps {
  copy: Copy;
  /** a match is connecting or playing */
  locked: boolean;
  finished: boolean;
  onKickoff: () => void;
  onNewMatch: () => void;
}

const ORDINALS = ["1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th"];
export const ordinal = (rank: number | undefined): string => (rank === undefined ? "" : (ORDINALS[rank - 1] ?? `${rank}th`));

export function CandidateStrip(props: StripProps) {
  const t = props.copy.trials.desk;
  const pack = web.pack;
  const cachedOnly = liveNarrator === null || !deskCandidates.includes(liveNarrator);
  const referee = web.results.referee;
  return (
    <section className="mp-above tr-cand" aria-label={t.narrator}>
      <div className="tr-cand-field">
        <label htmlFor="tr-narrator" className="tr-hd">
          {t.narrator}
        </label>
        <select id="tr-narrator" className="mp-select" value={props.narrator} disabled={props.locked || deskCandidates.length === 0} onChange={(e) => props.onNarrator(e.target.value)}>
          {deskCandidates.map((id) => (
            <option key={id} value={id}>
              {`${id} · ${ordinal(rankOf(id))} · ${id === liveNarrator ? t.live : fill(t.cachedOption, { pack })}`}
            </option>
          ))}
        </select>
        <span className="tr-sub">{fill(t.narratorHelp, { pack })}</span>
        {cachedOnly ? <span className="tr-sub tr-note">{t.noLive}</span> : null}
      </div>
      <div className="tr-cand-field">
        <span className="tr-hd">{t.referee}</span>
        <span className="tr-cand-referee">{fill(t.refereeLine, { judge: referee.judge, auditor: referee.auditor.replace(/^.*\(([^)]+)\)$/, "$1") })}</span>
      </div>
      <div className="tr-cand-field tr-cand-fixture">
        <label htmlFor="tr-fixture" className="tr-hd">
          {t.fixture}
        </label>
        <select id="tr-fixture" className="mp-select" value={props.fixture} disabled={props.locked} onChange={(e) => props.onFixture(e.target.value)}>
          {web.fixtures.map((f) => (
            <option key={f.id} value={f.id}>
              {fill(t.fixtureOption, { n: fixtureNumber(f.id), home: f.home, away: f.away, brief: f.brief })}
            </option>
          ))}
        </select>
        <span className="tr-cand-traps">
          {trapLabels(props.fixture).map((label, i) => (
            <span key={i} className="tr-chip">
              {label}
            </span>
          ))}
        </span>
      </div>
      <div className="tr-cand-go">
        <span className="mp-lift">
          <button type="button" className="mp-btn mp-btn--primary" onClick={props.finished ? props.onNewMatch : props.onKickoff} disabled={!props.finished && (props.locked || props.narrator === "")}>
            <i className="mp-btn-dot" aria-hidden="true" />
            {props.finished ? props.copy.setup.newMatch : props.cachedMode ? t.runCached : t.runLive}
          </button>
        </span>
      </div>
      {props.fallback ? (
        <div role="status" className="tr-cand-fallback">
          <span>{fill(t.fallback, { pack })}</span>
          <span className="mp-lift">
            <button type="button" className="mp-btn" onClick={props.onFallback}>
              {t.fallbackButton}
            </button>
          </span>
        </div>
      ) : null}
    </section>
  );
}
