import type { Copy, Lang } from "@/desk/copy";
import type { Mode } from "@/desk/reviewParams";
import { Scorebug } from "./Scorebug";
import { SegmentedControl } from "./SegmentedControl";
import { Wordmark } from "./Wordmark";

interface HeaderBarProps {
  copy: Copy;
  homeShort: string;
  awayShort: string;
  score: { home: number; away: number };
  clock: string;
  status: "live" | "fullTime";
  mode: Mode;
  lang: Lang;
  onMode: (mode: Mode) => void;
  onLang: (lang: Lang) => void;
}

export function HeaderBar({ copy, homeShort, awayShort, score, clock, status, mode, lang, onMode, onLang }: HeaderBarProps) {
  const h = copy.header;
  return (
    <header className="mp-header mp-above">
      <Wordmark first={copy.wordmark.first} second={copy.wordmark.second} />
      <Scorebug
        label={h.score}
        homeShort={homeShort}
        awayShort={awayShort}
        home={score.home}
        away={score.away}
        clock={clock}
        status={status}
        statusText={status === "live" ? h.live : h.fullTime}
      />
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
    </header>
  );
}
