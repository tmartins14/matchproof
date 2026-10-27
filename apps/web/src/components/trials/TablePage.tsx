import { copy, fill } from "@/desk/copy";
import { candidateById, web } from "@/trials/data";
import { seconds } from "@/trials/format";
import { LeagueTable, candidateCount } from "./LeagueTable";
import { Shell } from "./Shell";

function Hero() {
  const t = copy.en.trials;
  const h = web.hero;
  return (
    <section className="tr-card tr-hero">
      <div className="tr-hd">{t.hero.kicker}</div>
      {h ? (
        <h1 className="tr-h1">
          {h.sole ? (
            <span className="tr-h1-line">{fill(t.hero.cleared, { id: h.sole.candidate, o: h.sole.overturned, n: h.sole.total })}</span>
          ) : (
            <>
              <span className="tr-h1-line">{fill(t.hero.clearedMany, { ids: h.cleared.join(", ") })}</span>
              {h.fewest ? <span className="tr-h1-line tr-h1-line--sub">{fill(t.hero.fewest, { id: h.fewest.candidate, o: h.fewest.overturned, n: h.fewest.total })}</span> : null}
            </>
          )}
          {h.worst ? <span className="tr-h1-line tr-h1-line--sub">{fill(h.sole ? t.hero.worst : t.hero.worstMany, { id: h.worst.candidate, o: h.worst.overturned, n: h.worst.total })}</span> : null}
        </h1>
      ) : (
        <>
          <h1 className="tr-h1">{fill(t.hero.headline, { models: candidateCount(), fixtures: web.fixtures.length })}</h1>
          <p className="tr-body">{t.hero.how}</p>
        </>
      )}
      <p className="tr-body">{t.hero.trapDef}</p>
    </section>
  );
}

function Referee() {
  const t = copy.en.trials.referee;
  const r = web.results.referee;
  const self = web.results.candidates.filter((c) => c.self_audited).map((c) => c.id);
  return (
    <section className="tr-card">
      <div className="tr-hd">{t.title}</div>
      <div className="tr-line">{fill(t.checker, { name: r.checker })}</div>
      <div className="tr-line">{fill(t.judge, { name: r.judge })}</div>
      <div className="tr-line">{fill(t.auditor, { name: r.auditor })}</div>
      <div className="tr-body">{t.fixed}</div>
      {web.results.candidates.some((c) => c.id === r.judge) ? (
        <div className="tr-body tr-note">{fill(t.selfJudged, { name: r.judge })}</div>
      ) : null}
      {self.map((id) => (
        <div key={id} className="tr-body tr-note">
          {fill(t.selfAudited, { name: id })}
        </div>
      ))}
    </section>
  );
}

function Scoring() {
  const t = copy.en;
  const rows = [
    ["verified", t.verdict.verified, "+3"],
    ["rephrased", t.verdict.rephrased, "+1"],
    ["blocked", t.verdict.blocked, "−3"],
  ] as const;
  return (
    <section className="tr-card">
      <div className="tr-hd">{t.trials.scoring.title}</div>
      {rows.map(([key, label, pts]) => (
        <div key={key} className="tr-score">
          <span className={`mp-stamp mp-stamp--${key}`}>{label}</span>
          <span className="tr-score-pts">{pts}</span>
        </div>
      ))}
      <div className="tr-body">{t.trials.scoring.held}</div>
    </section>
  );
}

function Picks() {
  const t = copy.en.trials.picks;
  const { live_feed: live, budget, not_cleared: out, sole } = web.picks;
  if (!live && !budget && !out) return null;
  return (
    <section className="tr-picks" aria-label="Picks">
      {sole ? (
        <div className="tr-card">
          <div className="tr-hd">{t.sole}</div>
          <div className="tr-line">
            {fill(sole.usd_per_match === null ? t.soleLineNoPrice : t.soleLine, { id: sole.candidate, s: seconds(sole.p90_ms), usd: sole.usd_per_match?.toFixed(4) ?? "" })}
          </div>
        </div>
      ) : null}
      {!sole && live ? (
        <div className="tr-card">
          <div className="tr-hd">{t.live}</div>
          <div className="tr-line">{fill(t.liveLine, { id: live.candidate, s: seconds(live.p90_ms) })}</div>
        </div>
      ) : null}
      {!sole && budget ? (
        <div className="tr-card">
          <div className="tr-hd">{t.budget}</div>
          <div className="tr-line">{fill(t.budgetLine, { id: budget.candidate, usd: budget.usd_per_match.toFixed(4) })}</div>
        </div>
      ) : null}
      {out ? (
        <div className="tr-card">
          <div className="tr-hd">{t.notCleared}</div>
          <div className="tr-line">{out.map((id) => candidateById(id)?.id ?? id).join(", ")}</div>
        </div>
      ) : null}
    </section>
  );
}

function Footer() {
  const t = copy.en.trials.footer;
  return (
    <section className="tr-footer">
      <div className="tr-card">
        <div className="tr-hd">{t.relegation}</div>
        <div className="tr-body">{t.relegationBody}</div>
      </div>
      <div className="tr-card">
        <div className="tr-hd">{t.rerun}</div>
        <div className="tr-body">{t.rerunBody}</div>
      </div>
    </section>
  );
}

function NextUp() {
  if (web.next_up.length === 0) return null;
  return (
    <section className="tr-nextup">
      <span className="tr-hd">{copy.en.trials.nextUp.title}</span>
      <ul>
        {web.next_up.map((n) => (
          <li key={n.model}>
            <strong>{n.model}</strong> <span className="tr-sub">{n.reason}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** The Table: who do you put on air. */
export function TablePage() {
  return (
    <Shell>
      <div className="tr-strip">
        <Hero />
        <Referee />
        <Scoring />
      </div>
      <LeagueTable />
      <Picks />
      <Footer />
      <NextUp />
    </Shell>
  );
}
