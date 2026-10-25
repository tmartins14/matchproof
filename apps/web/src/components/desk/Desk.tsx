"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { copy as copies, type Lang } from "@/desk/copy";
import type { DeskFixture } from "@/desk/fixture";
import { formatClock } from "@/desk/format";
import { buildModel } from "@/desk/model";
import { buildPitch } from "@/desk/pitchModel";
import { buildRail } from "@/desk/railModel";
import type { Mode, ReviewState } from "@/desk/reviewParams";
import { buildMomentum, buildPipeline, buildStats, scoreAt } from "@/desk/statsModel";
import { composeBrief, firstSentence, setupSummary, tacticsOf, type Tactics } from "@/desk/tactics";
import { Pitch } from "@/viz/Pitch";
import { PitchLegend } from "@/viz/PitchLegend";
import { Backdrop } from "./Backdrop";
import { EvidenceRail } from "./EvidenceRail";
import { HeaderBar } from "./HeaderBar";
import { KeyMomentFeed } from "./KeyMomentFeed";
import { MatchSetupBar } from "./MatchSetupBar";
import { MomentumStrip } from "./MomentumStrip";
import { PipelineStrip } from "./PipelineStrip";
import { SectionTab } from "./SectionTab";
import { StatsPanel } from "./StatsPanel";
import { TickerPanel } from "./TickerPanel";

const STATUS_MS = 4000;
const GRID_SECONDS = 90 * 60;

interface DeskProps {
  fixture: DeskFixture;
  initial: ReviewState;
}

export function Desk({ fixture, initial }: DeskProps) {
  const [mode, setMode] = useState<Mode>(initial.mode);
  const [lang, setLang] = useState<Lang>(initial.lang);
  const [beatId, setBeatId] = useState(initial.beat);
  const [claimId, setClaimId] = useState(initial.claim);
  const [setupOpen, setSetupOpen] = useState(initial.setupOpen);
  const [tactics, setTactics] = useState<Tactics>(() => tacticsOf(fixture.brief));
  const [briefText, setBriefText] = useState<string | undefined>(undefined);
  const [custom, setCustom] = useState(false);
  const [note, setNote] = useState<string | undefined>(undefined);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => () => clearTimeout(timer.current), []);

  const c = copies[lang];
  const brief = fixture.brief;
  const storylineId = brief.storyline.id;
  const storyline = c.setup.storylines[storylineId] ?? brief.storyline.text;
  const model = useMemo(() => buildModel(fixture, { ...initial, mode, lang, beat: beatId, claim: claimId }), [fixture, initial, mode, lang, beatId, claimId]);
  const headlineOf = (kind: string): string => c.beatKind[kind as keyof typeof c.beatKind] ?? kind;

  const claim = model.selectedClaim;
  const beat = model.selectedBeat;
  const rail = claim ? buildRail(fixture, claim.claim.fact_ids, claim.claim.numbers.map((n) => n.fact_id), lang, c, beat?.side) : undefined;
  const beatEventIds = model.feed.find((r) => r.selected)?.claims.flatMap((v) => buildRail(fixture, v.claim.fact_ids, [], lang, c).events.map((e) => e.id)) ?? [];
  const pitch = buildPitch(fixture, model, rail?.events.map((e) => e.id) ?? [], beatEventIds);
  const stats = buildStats(fixture, model.clock, lang, c);
  const bars = buildMomentum(fixture, model.clock);
  const pipeline = buildPipeline(fixture, model);
  const score = scoreAt(fixture, model.clock);
  const eventById = new Map(fixture.events.map((e) => [e.id, e]));
  const ticker = fixture.ticker_event_ids.flatMap((id) => {
    const e = eventById.get(id);
    return e ? [{ id, label: c.eventType[e.type], who: e.player_id ? (fixture.players[e.player_id]?.name ?? "") : "", time: formatClock(e.t), side: e.side, isEvent: true }] : [];
  });

  const edited = (next: Tactics): void => {
    setTactics(next);
    setBriefText(composeBrief(c, next, storyline));
    setCustom(false);
    setNote(c.setup.rewritten);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setNote(undefined), STATUS_MS);
  };
  const typed = (text: string): void => {
    setBriefText(text);
    setCustom(true);
    setNote(undefined);
  };
  const title = beat ? headlineOf(beat.kind) : c.pitch.waiting;

  return (
    <div className="mp-root">
      <Backdrop />
      <HeaderBar copy={c} homeShort={brief.home.short} awayShort={brief.away.short} score={score} clock={formatClock(model.clock)} status="live" mode={mode} lang={lang} onMode={setMode} onLang={setLang} />
      <MatchSetupBar
        copy={c}
        summary={custom && briefText ? firstSentence(briefText) : setupSummary(c, tactics, brief, storyline, lang)}
        custom={custom}
        brief={briefText ?? brief.brief_text ?? composeBrief(c, tactics, storyline)}
        note={note}
        tactics={tactics}
        homeName={c.side.home}
        awayName={c.side.away}
        storylineId={storylineId}
        open={setupOpen}
        onToggle={() => setSetupOpen((v) => !v)}
        onBrief={typed}
        onTactics={edited}
      />
      <PipelineStrip copy={c} view={pipeline} running />
      <main className="mp-main mp-above">
        <section className="mp-col-match" aria-label={c.pitch.label}>
          <SectionTab as="h1" size="lg">{title}</SectionTab>
          <Pitch copy={c} view={pitch} headline={title} checking={claim?.verdict === "checking"} />
          <PitchLegend copy={c} />
          <div className="mp-twin">
            <StatsPanel view={stats} />
            <TickerPanel copy={c} rows={ticker} />
          </div>
          <MomentumStrip copy={c} bars={bars} model={model} gridSeconds={GRID_SECONDS} headlineOf={headlineOf} onPick={(id) => { setBeatId(id); setClaimId(undefined); }} />
        </section>
        <KeyMomentFeed copy={c} mode={mode} model={model} headlineOf={headlineOf} onBeat={(id) => { setBeatId(id); setClaimId(undefined); }} onClaim={(b, id) => { setBeatId(b); setClaimId(id); }} />
        {mode === "fan" ? null : <EvidenceRail copy={c} claim={claim} rail={rail} />}
      </main>
    </div>
  );
}
