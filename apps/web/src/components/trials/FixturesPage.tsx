"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef } from "react";
import { copy, fill } from "@/desk/copy";
import { scoredClaim, tableOrder, trapClocks, web } from "@/trials/data";
import { fixtureNumber, runDate, verdictKey } from "@/trials/format";
import { VerdictStamp } from "../desk/VerdictStamp";
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
            const trap = f.trap_beats[0]?.beat;
            const on = fixture === f.id;
            return (
              <div key={f.id} role="row" ref={on ? row : undefined} className={`tr-fx-row${on ? " tr-fx-row--on" : ""}`}>
                <div role="rowheader" className="tr-who">
                  <div className="tr-who-link">
                    {fixtureNumber(f.id)} · {f.home} v {f.away}
                  </div>
                  <div className="tr-sub">{f.brief}</div>
                  <div className="tr-cand-traps">
                    {trapClocks(f.id).map((clock, i) => (
                      <span key={i} className="tr-chip">
                        {fill(c.trials.desk.trap, { clock })}
                      </span>
                    ))}
                  </div>
                </div>
                {tableOrder.map((id) => {
                  const claim = trap ? scoredClaim(id, f.id, trap) : undefined;
                  return (
                    <div key={id} role="cell" className={`tr-fx-cell${focus === id ? " tr-fx-focus" : ""}`}>
                      {trap ? (
                        <Link href={`/compare/${f.id}/${trap}?focus=${id}`} className="tr-fx-link" aria-label={fill(t.open, { id, fixture: fixtureNumber(f.id) })}>
                          {claim && !claim.lost ? <VerdictStamp verdict={verdictKey(claim.verdict)} copy={c} /> : <span className="tr-chip">{t.noClaim}</span>}
                        </Link>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            );
          })}
        </div>
      </div>
    </Shell>
  );
}
