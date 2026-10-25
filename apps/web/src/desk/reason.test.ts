import { describe, expect, it } from "vitest";
import { copy } from "./copy";
import { fixture } from "./fixture";
import { buildRail, pickLead } from "./railModel";
import { displayReason, reasonLines } from "./reason";

describe("displayReason", () => {
  it("replaces the judge prefix with a category label", () => {
    expect(displayReason("Judge (overclaim): 'pressing hard' is not in the facts.", copy.en)).toBe("Overclaim: 'pressing hard' is not in the facts.");
  });
  it("replaces the voice rule prefix", () => {
    const raw = 'Voice rule evaluative-adjective broken by "tidy": A judgement the data cannot support; say what happened.';
    expect(displayReason(raw, copy.es)).toBe("Adjetivo sin respaldo: A judgement the data cannot support; say what happened.");
  });
  it("never shows the internal names", () => {
    for (const claim of fixture.claims) {
      for (const lang of ["en", "es"] as const) {
        expect(displayReason(claim.reason ?? "", copy[lang])).not.toMatch(/\bjudge\b|voice rule/i);
      }
    }
  });
});

describe("reconciler reasons", () => {
  const OUTSIDE = "Cited fact fx-compactness_home-since-ev-001888-to-t5865-29 is not in the beat's fact bundle.";
  const NUMBER = 'The number "808" matches no display rendering of the cited facts.';
  const INTERNAL = /\b(?:fx|ev|agg|win|ff)-|\bt\d+|bundle|_/i;

  it("maps the exact reason from the AMENDED claim, as two lines", () => {
    const raw = `${OUTSIDE}; ${NUMBER}`;
    expect(reasonLines(raw, copy.en)).toEqual(["Cites evidence from outside this moment", "Number not in the facts: 808"]);
    expect(reasonLines(raw, copy.es)).toEqual(["Cita datos de fuera de este momento", "Cifra que no está en los datos: 808"]);
  });
  it("maps a reason joined from three parts, in order", () => {
    const raw = `${OUTSIDE}; ${NUMBER}; The player "Pryce" is not named by any cited fact.`;
    expect(reasonLines(raw, copy.en)).toEqual(["Cites evidence from outside this moment", "Number not in the facts: 808", "Name not in the facts: Pryce"]);
  });
  it("maps every other format the reconciler and the checker write", () => {
    expect(reasonLines("The claim cites no facts.", copy.en)).toEqual(["Cites no facts"]);
    expect(reasonLines("'tighter' compares, but no before or change fact is cited.", copy.en)).toEqual(["Compares with nothing before it: tighter"]);
    expect(reasonLines("Judge did not answer: TimeoutError.", copy.en)).toEqual(["The check could not finish"]);
  });
  it("keeps a judge's sentence whole, even with a semicolon in it", () => {
    expect(reasonLines("Judge (overclaim): Says more than the facts; it never says why.", copy.en)).toEqual(["Overclaim: Says more than the facts; it never says why."]);
  });
  it("falls back to the category label alone for anything it does not know", () => {
    expect(reasonLines("Something new went wrong in fx-shot-ev-000123.", copy.en)).toEqual(["Wording"]);
    expect(reasonLines("Judge (overclaim): fx-shot-ev-000123 is not what it says.", copy.en)).toEqual(["Overclaim"]);
    expect(reasonLines("Judge (made-up): it is wrong.", copy.en)).toEqual(["Wording: it is wrong."]);
  });
  it("never lets an id, a clock token or the word bundle through", () => {
    const raws = [OUTSIDE, NUMBER, `${OUTSIDE}; ${NUMBER}`, "Cited fact fx-a-ev-000001 is not in the beat's fact bundle.", ...fixture.claims.flatMap((c) => (c.reason ? [c.reason] : []))];
    for (const raw of raws) {
      for (const lang of ["en", "es"] as const) {
        for (const line of reasonLines(raw, copy[lang])) expect(line, raw).not.toMatch(INTERNAL);
      }
    }
  });
});

describe("stat card", () => {
  const byId = new Map(fixture.facts.map((f) => [f.id, f]));
  it("prefers a distance over a duration", () => {
    const claim = fixture.claims.find((c) => c.id === "cl-001670-open_play_goal-01");
    const lead = pickLead((claim?.numbers ?? []).flatMap((n) => byId.get(n.fact_id) ?? []));
    expect(lead?.unit).toBe("m");
  });
  it("leaves the window off a single-minute span", () => {
    const claim = fixture.claims.find((c) => c.id === "cl-001670-open_play_goal-01");
    const rail = buildRail(fixture, claim?.fact_ids ?? [], (claim?.numbers ?? []).map((n) => n.fact_id), "en", copy.en);
    expect(rail.statCard?.window).toBeUndefined();
  });
});
