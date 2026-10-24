import { describe, expect, it } from "vitest";
import { copy } from "./copy";
import { fixture } from "./fixture";
import { buildRail, pickLead } from "./railModel";
import { displayReason } from "./reason";

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
