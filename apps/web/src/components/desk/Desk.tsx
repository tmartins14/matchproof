"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { MatchBrief } from "@/contracts/types";
import { copy as copies, fill, type Copy, type Lang } from "@/desk/copy";
import type { DeskData, Phase } from "@/desk/deskData";
import { formatClock } from "@/desk/format";
import { buildModel } from "@/desk/model";
import { buildPitch } from "@/desk/pitchModel";
import { buildRail, missingSources } from "@/desk/railModel";
import type { Mode, ReviewState } from "@/desk/reviewParams";
import { startingFrame, setupData } from "@/desk/startingShape";
import { rankOf } from "@/trials/data";
import { buildMomentum, buildPipeline, buildStats } from "@/desk/statsModel";
import { composeBrief, firstSentence, setupSummary, tacticsOf, type Tactics } from "@/desk/tactics";
import { getSource } from "@/live/api";
import type { Failure } from "@/live/api";
import type { LiveMatch, Speed } from "@/live/useLiveMatch";
import type { SourceRef } from "@/desk/deskData";
import { compareHref, scoredVerdicts, web } from "@/trials/data";
import { landedOf, recordOf } from "@/trials/record";
import { Pitch } from "@/viz/Pitch";
import { PitchLegend } from "@/viz/PitchLegend";
import { CandidateStrip, ordinal, type RunMode, type TrialsDeskProps } from "./CandidateStrip";
import { EvidenceRail } from "./EvidenceRail";
import { HeaderBar } from "./HeaderBar";
import { KeyMomentFeed } from "./KeyMomentFeed";
import { MatchSetupBar, type SetupActions } from "./MatchSetupBar";
import { MomentumStrip } from "./MomentumStrip";
import { PipelineStrip } from "./PipelineStrip";
import { SectionTab } from "./SectionTab";
import { StatsPanel } from "./StatsPanel";
import { TickerPanel } from "./TickerPanel";

const STATUS_MS = 4000;
const NOTICE_MS = 6000;
const GRID_SECONDS = 90 * 60;

interface DeskProps {
  data: DeskData;
  initial: ReviewState;
  /** The live controls; absent when the desk shows the static fixture. */
  live?: Omit<LiveMatch, "data" | "kickoff"> & {
    /** `mode` is the viewer's choice on the Trials desk; absent elsewhere */
    kickoff: (brief: MatchBrief, speed: Speed, mode?: RunMode) => Promise<MatchBrief | undefined>;
  };
  /** Set on the Trials desk: the narrator and fixture strip, cached replay and the RECORD tile. */
  trials?: TrialsDeskProps;
}

const STREAMING: Phase[] = ["connecting", "live", "focus", "freeze", "half_time"];

function withTactics(brief: MatchBrief, t: Tactics): MatchBrief {
  const side = (team: MatchBrief["home"], s: Tactics["home"]): MatchBrief["home"] => ({ ...team, formation: s.formation, press: s.dials[0], directness: s.dials[1], line_height: s.dials[2] });
  return { ...brief, home: side(brief.home, t.home), away: side(brief.away, t.away) };
}

/** `DESK · RUNNING <id> (<rank>)` during a run, `DESK · READY · <id> (<rank>)` otherwise, and `· LIVE` once the stream's status message has named the narrator. */
function deskLabelOf(c: Copy, trials: TrialsDeskProps, running: boolean): string {
  const model = trials.streamNarrator ?? trials.narrator;
  const label = fill(running ? c.trials.desk.label : c.trials.desk.labelReady, { model, rank: ordinal(rankOf(model)) });
  return trials.streamNarrator ? `${label} · ${c.trials.desk.live}` : label;
}

export function Desk({ data, initial, live, trials }: DeskProps) {
  const [mode, setMode] = useState<Mode>(initial.mode);
  const [lang, setLang] = useState<Lang>(initial.lang);
  const [beatId, setBeatId] = useState(initial.beat);
  const [claimId, setClaimId] = useState(initial.claim);
  const [setupOpen, setSetupOpen] = useState(initial.setupOpen);
  const [brief, setBrief] = useState<MatchBrief>(data.brief);
  const [briefText, setBriefText] = useState<string | undefined>(undefined);
  const [reading, setReading] = useState(false);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [speed, setSpeed] = useState<Speed>(3);
  const [fetched, setFetched] = useState<Record<string, SourceRef>>({});
  const [fetchedFor, setFetchedFor] = useState(data.match_id);
  const requested = useRef(new Set<string>());
  const [custom, setCustom] = useState(false);
  // A random or composed match, or edited tactics, is not a pack fixture: there is nothing to compare it with.
  const [packMatch, setPackMatch] = useState(true);
  const [shown, setShown] = useState<{ text: string; ms: number } | undefined>(undefined);
  const notify = (text: string, ms: number): void => setShown({ text, ms });
  const note = shown?.text;
  // A notice goes away on its own: the timer belongs to the notice, so a newer one restarts it.
  useEffect(() => {
    if (!shown) return;
    const timer = setTimeout(() => setShown(undefined), shown.ms);
    return () => clearTimeout(timer);
  }, [shown]);

  const c = copies[lang];
  const tactics = tacticsOf(brief);
  const view = useMemo(() => (data.phase === "pre" && live ? { ...data, brief } : data), [data, brief, live]);
  const storylineId = brief.storyline.id;
  const storyline = c.setup.storylines[storylineId] ?? brief.storyline.text;
  const model = useMemo(() => buildModel(view, { ...initial, mode, lang, beat: beatId, claim: claimId }), [view, initial, mode, lang, beatId, claimId]);
  const headlineOf = (kind: string): string => c.beatKind[kind as keyof typeof c.beatKind] ?? kind;

  const withSources = useMemo(() => ({ ...view, sources: { ...view.sources, ...fetched } }), [view, fetched]);
  const claim = model.selectedClaim;
  const beat = model.selectedBeat;
  const rail = claim ? buildRail(withSources, claim.claim.fact_ids, claim.claim.numbers.map((n) => n.fact_id), lang, c, beat?.side) : undefined;
  const beatEventIds = model.feed.find((r) => r.selected)?.claims.flatMap((v) => buildRail(view, v.claim.fact_ids, [], lang, c).events.map((e) => e.id)) ?? [];
  const pinned = Boolean(live && beatId);
  const pitch = buildPitch(view, model, rail?.events.map((e) => e.id) ?? [], beatEventIds, pinned, live ? startingFrame(brief) : undefined);
  const stats = buildStats(view, model.clock, lang, c);
  const bars = buildMomentum(view, model.clock);
  const pipeline = buildPipeline(view, model);
  const packFixture = trials !== undefined && packMatch;
  const tableVerdicts = trials?.playingCached ? scoredVerdicts(trials.narrator, trials.fixture) : undefined;
  const record = packFixture ? recordOf(landedOf(view.claims, tableVerdicts), web.points) : undefined;
  const narratorUpper = trials?.narrator.toUpperCase() ?? "";
  const compareFor = (beatId: string): string | undefined => (packFixture && trials ? compareHref(trials.fixture, beatId, trials.narrator) : undefined);
  const score = view.score;
  const eventById = new Map(view.events.map((e) => [e.id, e]));
  const ticker = view.ticker_event_ids.flatMap((id) => {
    const e = eventById.get(id);
    return e ? [{ id, label: c.eventType[e.type], who: e.player_id ? (view.players[e.player_id]?.name ?? "") : "", time: formatClock(e.t), side: e.side, isEvent: true }] : [];
  });

  const edited = (next: Tactics): void => {
    setBrief((b) => withTactics(b, next));
    setBriefText(composeBrief(c, next, storyline));
    setCustom(false);
    setPackMatch(false);
    notify(c.setup.rewritten, STATUS_MS);
  };
  const typed = (text: string): void => {
    setBriefText(text);
    setCustom(true);
    setPackMatch(false);
    setShown(undefined);
  };
  const title = beat ? headlineOf(beat.kind) : c.pitch.waiting;

  const phase = view.phase;
  const streaming = STREAMING.includes(phase);
  const failureText = (reason: Failure): string => ({ rate_limit: c.setup.rateLimit, busy: c.setup.busy, rejected: c.setup.briefRejected, finished: c.setup.finished, unreachable: c.setup.unreachable })[reason];
  const unpin = (): void => {
    setBeatId(undefined);
    setClaimId(undefined);
  };

  // A notice from the server shows for a few seconds; so does a refusal from the API.
  // Each is announced once, when it first appears (state adjusted during render, not in an effect).
  const lastNotice = data.notices.at(-1);
  const [announced, setAnnounced] = useState({ notice: 0, problem: 0 });
  if (lastNotice && lastNotice.id !== announced.notice) {
    setAnnounced({ ...announced, notice: lastNotice.id });
    notify(lastNotice.text, NOTICE_MS);
  } else if (live?.problem && live.problem.id !== announced.problem) {
    setAnnounced({ ...announced, problem: live.problem.id });
    notify(failureText(live.problem.reason), NOTICE_MS);
  }

  // The rail asks for the sources the stream does not carry (windows, aggregates, freeze frames).
  const railFactIds = claim ? [...claim.claim.fact_ids, ...claim.claim.numbers.map((n) => n.fact_id)] : [];
  const wanted = live && fetchedFor === data.match_id ? missingSources(view, railFactIds).filter((id) => !(id in fetched)) : [];
  const wantedKey = wanted.join(",");
  useEffect(() => {
    for (const id of wanted) {
      const key = `${data.match_id}/${id}`;
      if (requested.current.has(key)) continue;
      requested.current.add(key);
      void getSource(data.match_id, id).then((source) => {
        if (source) setFetched((f) => ({ ...f, [id]: source }));
        else requested.current.delete(key);
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wantedKey, data.match_id]);
  if (fetchedFor !== data.match_id) {
    setFetchedFor(data.match_id);
    setFetched({});
  }

  const kickoff = (mode?: RunMode): void => {
    if (!live) return;
    unpin();
    const text = briefText ?? brief.brief_text;
    void live.kickoff(text ? { ...brief, brief_text: text } : brief, speed, mode).then((played) => {
      if (played) setBrief(played);
    });
  };

  const actions: SetupActions | undefined = live
    ? {
        locked: streaming,
        inStrip: trials !== undefined,
        cachedOnly: trials?.cachedMode === true,
        finished: phase === "full_time" || phase === "error",
        reading,
        warnings,
        speed,
        storylines: Object.keys(setupData.storylines).map((id) => ({ id, text: c.setup.storylines[id as keyof typeof c.setup.storylines] ?? id })),
        onSpeed: setSpeed,
        onStoryline: (id) => {
          const story = setupData.storylines[id];
          if (!story) return;
          setBrief((b) => ({ ...b, storyline: { id: id as MatchBrief["storyline"]["id"], text: story.text }, planted_beats: story.planted_beats }));
          setBriefText(composeBrief(c, tactics, c.setup.storylines[id as keyof typeof c.setup.storylines] ?? story.text));
          setCustom(false);
          setPackMatch(false);
        },
        onRandomize: () => {
          void live.randomize().then((r) => {
            if (!r.ok) return notify(failureText(r.reason), NOTICE_MS);
            setBrief(r.value.brief);
            setBriefText(r.value.brief.brief_text);
            setCustom(false);
            setPackMatch(false);
            setWarnings([]);
          });
        },
        onRead: () => {
          setReading(true);
          void live.compose(briefText ?? brief.brief_text ?? composeBrief(c, tactics, storyline)).then((r) => {
            setReading(false);
            if (!r.ok) return notify(failureText(r.reason), NOTICE_MS);
            setBrief(r.value.brief);
            setBriefText(r.value.brief_text);
            setWarnings(r.value.warnings);
            setCustom(false);
            setPackMatch(false);
          });
        },
        onKickoff: () => kickoff(),
        onNewMatch: () => {
          unpin();
          live.reset(brief);
        },
      }
    : undefined;
  const shownNote = phase === "error" ? c.setup.connectionLost : phase === "connecting" ? c.setup.connecting : note;
  const headerStatus = !live ? "live" : phase === "pre" || phase === "connecting" ? "pre" : phase === "half_time" ? "halfTime" : phase === "full_time" ? "fullTime" : phase === "error" ? "off" : "live";

  return (
    <div className="mp-above">
      <div className="mp-shell mp-above">
      <HeaderBar copy={c} deskLabel={trials ? deskLabelOf(c, trials, streaming) : undefined} replayText={trials?.playingCached ? fill(c.trials.desk.replay, { pack: web.pack }) : undefined} cachedChip={trials?.playingCached ? fill(c.trials.desk.cachedChip, { pack: web.pack }) : undefined} homeShort={brief.home.short} awayShort={brief.away.short} score={score} clock={formatClock(model.clock)} status={headerStatus} mode={mode} lang={lang} onMode={setMode} onLang={setLang} />
      {trials ? (
        <CandidateStrip {...trials} copy={c} locked={streaming} finished={phase === "full_time" || phase === "error"} onRun={kickoff} onNewMatch={actions?.onNewMatch ?? (() => undefined)} />
      ) : null}
      <MatchSetupBar
        copy={c}
        summary={custom && briefText ? firstSentence(briefText) : setupSummary(c, tactics, brief, storyline, lang)}
        custom={custom}
        brief={briefText ?? brief.brief_text ?? composeBrief(c, tactics, storyline)}
        note={shownNote}
        tactics={tactics}
        homeName={c.side.home}
        awayName={c.side.away}
        storylineId={storylineId}
        open={setupOpen}
        onToggle={() => setSetupOpen((v) => !v)}
        onBrief={typed}
        onTactics={edited}
        actions={actions}
      />
      <PipelineStrip copy={c} view={pipeline} running={!live || streaming} record={record ? { view: record, title: fill(c.trials.desk.recordTitle, { model: narratorUpper }) } : undefined} />
      <main className="mp-main mp-above">
        <section className="mp-col-match" aria-label={c.pitch.label}>
          <div className="mp-pitch-head">
            <SectionTab as="h1" size="lg">{title}</SectionTab>
            {pinned ? (
              <span className="mp-lift">
                <button type="button" className="mp-btn" onClick={unpin}>
                  {c.pitch.followLive}
                </button>
              </span>
            ) : null}
          </div>
          <Pitch copy={c} view={pitch} headline={title} checking={claim?.verdict === "checking"} />
          <PitchLegend copy={c} />
          <div className="mp-twin">
            <StatsPanel view={stats} />
            <TickerPanel copy={c} rows={ticker} />
          </div>
          <MomentumStrip copy={c} bars={bars} model={model} gridSeconds={GRID_SECONDS} headlineOf={headlineOf} onPick={(id) => { setBeatId(id); setClaimId(undefined); }} />
        </section>
        <KeyMomentFeed copy={c} mode={mode} model={model} badge={trials ? fill(c.trials.desk.badge, { model: narratorUpper }) : undefined} compareHref={compareFor} headlineOf={headlineOf} onBeat={(id) => { setBeatId(id); setClaimId(undefined); }} onClaim={(b, id) => { setBeatId(b); setClaimId(id); }} />
        {mode === "fan" ? null : <EvidenceRail copy={c} claim={claim} rail={rail} />}
      </main>
      </div>
    </div>
  );
}
