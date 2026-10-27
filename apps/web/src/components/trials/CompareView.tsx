"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo } from "react";
import { copy, fill } from "@/desk/copy";
import type { PitchView } from "@/desk/pitchModel";
import { beatsOf, firstTrapBeat, fixtureById, momentOf, web } from "@/trials/data";
import { fixtureNumber } from "@/trials/format";
import { Pitch } from "@/viz/Pitch";
import { NarratorCard } from "./NarratorCard";
import { Shell } from "./Shell";

function pitchOf(fixture: string, beat: string): PitchView | undefined {
  const m = momentOf(fixture, beat);
  const f = fixtureById(fixture);
  if (!m?.freeze || !f) return undefined;
  const players = [...f.match_brief.home.players, ...f.match_brief.away.players];
  return {
    frame: m.freeze as PitchView["frame"],
    caption: { kind: "freeze", t: m.freeze.t },
    marks: [],
    highlight: undefined,
    goalkeepers: new Set(players.filter((p) => p.slot === 0).map((p) => p.id)),
  };
}

/** Same moment, every narrator, one referee. */
export function CompareView({ fixture, beat }: { fixture: string; beat: string }) {
  const t = copy.en.trials.compare;
  const router = useRouter();
  const focus = useSearchParams().get("focus");
  const moment = momentOf(fixture, beat);
  const f = fixtureById(fixture);
  const beats = beatsOf(fixture);
  const at = beats.indexOf(beat);
  const prev = at > 0 ? beats[at - 1] : undefined;
  const next = at >= 0 && at < beats.length - 1 ? beats[at + 1] : undefined;
  const pitch = useMemo(() => pitchOf(fixture, beat), [fixture, beat]);

  useEffect(() => {
    if (focus) document.getElementById(`card-${focus}`)?.scrollIntoView({ block: "center" });
  }, [focus, beat]);

  useEffect(() => {
    const go = (e: KeyboardEvent): void => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const target = e.key === "ArrowLeft" ? prev : e.key === "ArrowRight" ? next : undefined;
      if (target) router.push(`/compare/${fixture}/${target}${focus ? `?focus=${focus}` : ""}`);
    };
    window.addEventListener("keydown", go);
    return () => window.removeEventListener("keydown", go);
  }, [prev, next, fixture, focus, router]);

  if (!moment || !f) {
    return (
      <Shell>
        <p className="tr-body">{t.noRow}</p>
      </Shell>
    );
  }
  const query = focus ? `&focus=${focus}` : "";
  const keep = focus ? `?focus=${focus}` : "";
  const trapLabel = new Map(f.trap_beats.map((tb, i) => [tb.beat, (f.traps[i]?.label ?? "").replace(/\s+\S+$/, "")]));
  const momentText = (id: string): string => {
    const m = momentOf(fixture, id);
    const clock = m?.clock ?? "";
    const trap = trapLabel.get(id);
    return trap !== undefined ? fill(t.trapOption, { clock, label: trap }) : fill(t.momentOption, { clock, label: (m?.kind ?? "").replace(/_/g, " ") });
  };
  const step = (to: string | undefined, label: string, glyph: string) =>
    to ? (
      <Link className="tr-btn tr-btn--sm" href={`/compare/${fixture}/${to}${focus ? `?focus=${focus}` : ""}`} aria-label={label}>
        {glyph}
      </Link>
    ) : (
      <span className="tr-btn tr-btn--sm tr-btn--off" aria-hidden="true">
        {glyph}
      </span>
    );

  return (
    <Shell>
      <div className="tr-crumb">
        <div className="tr-crumb-field">
          <label htmlFor="cmp-fixture" className="tr-hd">
            {t.fixtureSelect}
          </label>
          <select
            id="cmp-fixture"
            className="mp-select"
            value={fixture}
            onChange={(e) => {
              const first = firstTrapBeat(e.target.value) ?? beatsOf(e.target.value)[0];
              if (first) router.push(`/compare/${e.target.value}/${first}${keep}`);
            }}
          >
            {web.fixtures.map((x) => (
              <option key={x.id} value={x.id}>
                {fill(t.fixtureOption, { n: fixtureNumber(x.id), home: x.home, away: x.away, brief: x.brief })}
              </option>
            ))}
          </select>
        </div>
        <div className="tr-crumb-field">
          <label htmlFor="cmp-moment" className="tr-hd">
            {t.momentSelect}
          </label>
          <select id="cmp-moment" className="mp-select" value={beat} onChange={(e) => router.push(`/compare/${fixture}/${e.target.value}${keep}`)}>
            {beats.map((id) => (
              <option key={id} value={id}>
                {momentText(id)}
              </option>
            ))}
          </select>
        </div>
        <span className="tr-chip tr-chip--light">{fill(t.chip, { clock: moment.clock, label: moment.kind.replace(/_/g, " ") })}</span>
        <span className="tr-steps-nav">
          {step(prev, t.prev, "←")}
          <span className="tr-mono">{fill(t.position, { i: at + 1, n: beats.length })}</span>
          {step(next, t.next, "→")}
        </span>
      </div>
      <div className="tr-compare">
        <div className="tr-evidence">
          <section className="tr-card">
            <div className="tr-card-head">
              <span className="tr-hd">{fill(t.freeze, { clock: moment.clock })}</span>
              <span className="tr-mono">{beat}</span>
            </div>
            {pitch ? <Pitch copy={copy.en} view={pitch} headline={moment.kind.replace(/_/g, " ")} checking={false} /> : null}
            <div className="tr-sub">{t.sameFrame}</div>
          </section>
          <section className="tr-card">
            <div className="tr-hd">{t.factsTitle}</div>
            {moment.facts.map((x) => (
              <div key={x.id}>
                <div className="tr-fact">
                  {x.label}: {x.text}
                </div>
                <div className="tr-mono tr-dim">{x.id}</div>
              </div>
            ))}
          </section>
          <section className="tr-card">
            <div className="tr-hd">{t.sourcesTitle}</div>
            {moment.sources.map((s) => (
              <div key={s.id} className="tr-ev">
                <span className="tr-mono">{s.id}</span>
                <span>
                  {s.type.replace(/_/g, " ")}
                  {s.player ? `, ${s.player}` : ""}
                </span>
                <span className="tr-mono">{s.clock}</span>
              </div>
            ))}
          </section>
        </div>
        <div className="tr-narrators">
          <div className="tr-narrators-head">
            <h1 className="tr-h1 tr-h1--sm">{fill(t.headline, { n: web.order.length })}</h1>
            <p className="tr-sub">{t.note}</p>
          </div>
          <div className="tr-cards">
            {web.order.map((id) => (
              <NarratorCard key={id} candidate={id} fixture={fixture} beat={beat} focused={id === focus} />
            ))}
            <section className="tr-card tr-card--note">
              <div className="tr-hd">{t.refereeNoteTitle}</div>
              <p className="tr-body">{t.refereeNote}</p>
              <Link className="tr-link" href={`/fixtures?fixture=${fixture}${query}`}>
                {t.fixtureLink} →
              </Link>
            </section>
          </div>
        </div>
      </div>
    </Shell>
  );
}
