"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef } from "react";
import { copy, fill } from "@/desk/copy";
import { tableOrder, trapLabels, web } from "@/trials/data";
import { fixtureNumber, runDate, verdictKey } from "@/trials/format";
import { Shell } from "./Shell";

function Header() {
  const t = copy.en.trials.fixtures;
  const seeds = web.fixtures.map((f) => f.seed);
  const per = web.results.summary[0]?.claims ?? 0;
  return (
    <section className="tr-strip">
      <div className="tr-card tr-hero">
        <h1 className="tr-h1 tr-h1--sm">{t.title}</h1>
        <p className="tr-body tr-note">{t.refereeNote}</p>
      </div>
      <div className="tr-card">
        <div className="tr-hd">{fill(t.pack, { pack: web.pack, from: Math.min(...seeds), to: Math.max(...seeds) })}</div>
        <div className="tr-line">{fill(t.scored, { n: per })}</div>
        <div className="tr-sub">{fill(t.lastRun, { date: runDate(web.results.run_at) })}</div>
      </div>
      <div className="tr-card">
        <div className="tr-hd">{t.howTitle}</div>
        <p className="tr-body">{t.how}</p>
      </div>
      <div className="tr-card">
        <div className="tr-hd">{t.stampTitle}</div>
        <p className="tr-body">{t.stamp}</p>
      </div>
    </section>
  );
}

export function FixturesPage() {
  const t = copy.en.trials.fixtures;
  const c = copy.en;
  const params = useSearchParams();
  const fixture = params.get("fixture");
  const focus = params.get("focus");
  const row = useRef<HTMLDivElement | null>(null);
  useEffect(() => row.current?.scrollIntoView({ block: "center" }), [fixture]);
  return (
    <Shell>
      <Header />
      <p className="tr-body tr-gridnote">{t.gridNote}</p>
      <div className="tr-table-wrap">
        <div role="table" aria-label={t.title} className="tr-fx" style={{ ["--cols" as string]: tableOrder.length }}>
          <div role="row" className="tr-fx-row tr-head">
            <div role="columnheader" className="tr-hd">
              {t.colFixture}
            </div>
            {tableOrder.map((id) => (
              <div key={id} role="columnheader" className={`tr-hd tr-hd--c${focus === id ? " tr-fx-focus" : ""}`}>
                {id}
              </div>
            ))}
          </div>
          {web.fixtures.map((f) => {
            const on = fixture === f.id;
            return (
              <div key={f.id} role="row" ref={on ? row : undefined} className={`tr-fx-row${on ? " tr-fx-row--on" : ""}`}>
                <div role="rowheader" className="tr-who">
                  <div className="tr-who-link">
                    {fixtureNumber(f.id)} · {f.home} v {f.away}
                  </div>
                  <div className="tr-sub">{f.brief}</div>
                  <div className="tr-cand-traps">
                    {trapLabels(f.id).map((label, i) => (
                      <span key={i} className="tr-chip">
                        {label}
                      </span>
                    ))}
                  </div>
                </div>
                {tableOrder.map((id) => (
                  <div key={id} role="cell" className={`tr-fx-cell${focus === id ? " tr-fx-focus" : ""}`}>
                    <span className="tr-fx-stamps">
                      {(web.trap_verdicts[id]?.[f.id] ?? []).map((v) => {
                        const word = v.verdict === "HELD" ? t.noAnswer : c.verdict[verdictKey(v.verdict)];
                        return (
                          <Link
                            key={v.beat}
                            href={`/compare/${f.id}/${v.beat}?focus=${id}`}
                            className={`tr-fx-mini tr-fx-mini--${v.verdict}`}
                            title={fill(t.stampTip, { label: v.label, verdict: word })}
                            aria-label={fill(t.stampName, { l: v.verdict.charAt(0), clock: v.clock, label: v.label, verdict: word, id, fixture: fixtureNumber(f.id) })}
                          >
                            <span className="tr-fx-letter">
                              {v.verdict[0]}
                            </span>{" "}
                            <span className="tr-fx-clock">
                              {v.clock}
                            </span>
                          </Link>
                        );
                      })}
                    </span>
                  </div>
                ))}
              </div>
            );
          })}
        </div>
      </div>
    </Shell>
  );
}
