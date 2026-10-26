import { describe, expect, it } from "vitest";
import { copy } from "@/desk/copy";
import { cellOf, tableOrder, web } from "./data";
import { verdictKey } from "./format";

describe("the Fixtures grid", () => {
  const cells = web.fixtures.flatMap((f) => {
    const beat = f.trap_beats[0]?.beat ?? "";
    return tableOrder.map((candidate) => ({ candidate, fixture: f.id, beat }));
  });

  it("has a cell for every candidate on every fixture's first trap beat", () => {
    expect(cells.length).toBe(web.fixtures.length * tableOrder.length);
    for (const c of cells) expect(cellOf(c.candidate, c.fixture, c.beat), `${c.candidate} ${c.fixture}`).toBeDefined();
  });

  it("shows the Table's verdict for the scored row, for every candidate and fixture", () => {
    for (const c of cells) {
      const row = web.results.claims.find((r) => r.candidate === c.candidate && r.fixture === c.fixture && r.beat === c.beat && r.scored);
      expect(cellOf(c.candidate, c.fixture, c.beat)?.verdict, `${c.candidate} ${c.fixture}`).toBe(row?.verdict);
    }
  });

  it("scores a lost row as the Table does: no_answer is HELD, the other lost kinds are OVERTURNED", () => {
    const lost = web.results.claims.filter((r) => r.lost !== null && r.scored);
    expect(lost.length).toBeGreaterThan(0);
    for (const r of lost) {
      const cell = cellOf(r.candidate, r.fixture, r.beat);
      expect(cell?.verdict).toBe(r.lost === "no_answer" ? "HELD" : "OVERTURNED");
      expect(cell?.noAnswer).toBe(r.lost === "no_answer");
      expect(Boolean(cell?.why)).toBe(r.lost !== "no_answer");
      expect(verdictKey(cell!.verdict)).toBe(r.lost === "no_answer" ? "delayed" : "blocked");
    }
  });

  it("explains an overturned lost row in plain English", () => {
    expect(Object.values(copy.en.trials.lostReason)).toEqual(["cited a fact that doesn't exist", "output could not be read", "wrote no claim", "no answer from the narrator"]);
  });
});
