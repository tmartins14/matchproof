import { describe, expect, it } from "vitest";
import { beatsOf, candidateById, clockOfWorst, firstTrapBeat, momentOf, rankOf, scoredClaim, summaryOf, tableOrder, web, worstOf } from "./data";
import { amendedParts, compactTokens, failParts, fixtureNumber, seconds, verdictKey } from "./format";

describe("trials data", () => {
  it("draws ranks and order from the export, unmeasured rows last and unranked", () => {
    const ranked = tableOrder.filter((id) => rankOf(id) !== undefined);
    expect(tableOrder.slice(0, ranked.length)).toEqual(ranked);
    expect(ranked.map((id) => rankOf(id))).toEqual(ranked.map((_, i) => i + 1));
    for (const id of tableOrder) {
      expect(web.measured[id]).toBe(rankOf(id) !== undefined);
      expect(worstOf(id) === null).toBe(!web.measured[id]);
    }
  });

  it("resolves every worst moment to a moment with a clock", () => {
    for (const id of tableOrder) {
      const w = worstOf(id);
      if (!w) continue;
      expect(momentOf(w.fixture, w.beat)).toBeDefined();
      expect(clockOfWorst(w)).toMatch(/′$/);
      expect(scoredClaim(id, w.fixture, w.beat)?.verdict).toBe(w.verdict);
    }
  });

  it("has a first trap beat that is a moment, for every fixture", () => {
    for (const f of web.fixtures) {
      const beat = firstTrapBeat(f.id);
      expect(beat && momentOf(f.id, beat)).toBeTruthy();
    }
  });

  it("lists every candidate and gives every summary row a candidate", () => {
    for (const row of web.results.summary) expect(candidateById(row.candidate)).toBeDefined();
    expect(summaryOf("nobody")).toBeUndefined();
  });

  it("keeps beats in play order", () => {
    for (const f of web.fixtures) {
      const ts = beatsOf(f.id).map((b) => momentOf(f.id, b)?.t ?? 0);
      expect(ts).toEqual([...ts].sort((a, b) => a - b));
    }
  });
});

describe("trials format", () => {
  it("formats seconds, fixture numbers and tokens", () => {
    expect(seconds(1900)).toBe("1.9");
    expect(seconds(29509)).toBe("29.5");
    expect(fixtureNumber("fx-03")).toBe("03");
    expect(compactTokens(1_500_000)).toBe("1.5M");
    expect(compactTokens(91_400)).toBe("91k");
  });

  it("maps Trials verdicts onto the Desk's", () => {
    expect([verdictKey("STANDS"), verdictKey("AMENDED"), verdictKey("OVERTURNED"), verdictKey("HELD")]).toEqual(["verified", "rephrased", "blocked", "delayed"]);
  });

  it("splits an amended draft only when the pieces rebuild the aired text", () => {
    const row = { draft_text: "Ashford are down to nine men now", text: "Ashford are down to ten men now", failed_span: "nine", corrected_span: "ten" };
    expect(amendedParts(row)).toEqual({ before: "Ashford are down to ", failed: "nine", corrected: "ten", after: " men now" });
    expect(amendedParts({ ...row, text: "Something else entirely" })).toBeUndefined();
    expect(amendedParts({ ...row, failed_span: null })).toBeUndefined();
  });

  it("orders the fail profile biggest first", () => {
    expect(failParts({ numbers: 0.2, overclaim: 0.8 }).map((p) => p.bucket)).toEqual(["overclaim", "numbers"]);
  });
});
