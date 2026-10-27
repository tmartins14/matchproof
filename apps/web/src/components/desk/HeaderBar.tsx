import type { Copy, Lang } from "@/desk/copy";
import type { Mode } from "@/desk/reviewParams";
import { Scorebug } from "./Scorebug";
import { SegmentedControl } from "./SegmentedControl";

interface HeaderBarProps {
  copy: Copy;
  homeShort: string;
  awayShort: string;
  score: { home: number; away: number };
  clock: string;
  status: "off" | "pre" | "live" | "halfTime" | "fullTime";
  /** `REPLAY · pack-v1`: shown in place of LIVE for the whole cached run */
  replayText?: string;
  mode: Mode;
  lang: Lang;
  onMode: (mode: Mode) => void;
  onLang: (lang: Lang) => void;
  /** `DESK · running <model> (<rank>)` */
  deskLabel?: string;
  /** `CACHED · pack-v1`, shown next to the clock while a cached replay runs */
  cachedChip?: string;
}

export function HeaderBar({ copy, homeShort, awayShort, score, clock, status, mode, lang, onMode, onLang, deskLabel, cachedChip, replayText }: HeaderBarProps) {
  const h = copy.header;
  return (
    <section className="mp-header mp-header--strip mp-above" aria-label={h.controls}>
      {deskLabel ? <span className="tr-hd tr-desk-label">{deskLabel}</span> : null}
      <Scorebug
        label={h.score}
        homeShort={homeShort}
        awayShort={awayShort}
        home={score.home}
        away={score.away}
        clock={clock}
        status={replayText && status === "live" ? "replay" : status}
        statusText={replayText && status === "live" ? replayText : { off: "", pre: h.pre, live: h.live, halfTime: h.halfTime, fullTime: h.fullTime }[status]}
      />
      {cachedChip ? <span className="tr-chip tr-chip--cached">{cachedChip}</span> : null}
      <div className="mp-controls">
        <SegmentedControl
          label={h.mode}
          value={mode}
          onChange={onMode}
          options={[
            { value: "fan", label: h.modes.fan },
            { value: "analyst", label: h.modes.analyst },
            { value: "producer", label: h.modes.producer },
          ]}
        />
        <SegmentedControl
          label={h.lang}
          value={lang}
          onChange={onLang}
          options={[
            { value: "en", label: h.langs.en },
            { value: "es", label: h.langs.es },
          ]}
        />
      </div>
    </section>
  );
}
