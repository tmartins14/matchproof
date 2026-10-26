import { describe, expect, it } from "vitest";
import { landedOf, recordOf, signedPts } from "./record";

const points = { STANDS: 3, AMENDED: 1, OVERTURNED: -3, HELD: 0 };

describe("the RECORD tile", () => {
  it("counts the first claim of each beat and adds the Table's points", () => {
    const claims = [
      { id: "cl-a-01", verdict: "verified" },
      { id: "cl-a-02", verdict: "blocked" }, // not the first claim of its beat
      { id: "cl-b-01", verdict: "rephrased" },
      { id: "cl-c-01", verdict: "blocked" },
      { id: "cl-d-01", verdict: "checking" },
    ];
    const view = recordOf(landedOf(claims), points);
    expect(view).toEqual({ STANDS: 1, AMENDED: 1, OVERTURNED: 1, CHECKING: 1, pts: 1 });
  });

  it("scores a held beat at the scale's value and does not count it as overturned", () => {
    const view = recordOf(["HELD", "STANDS"], points);
    expect(view).toMatchObject({ STANDS: 1, OVERTURNED: 0, pts: 3 });
  });

  it("uses the Table's verdict for a cached row, and the scored flag over the -01 suffix", () => {
    const table = new Map<string, "STANDS" | "HELD">([
      ["cl-a-02", "STANDS"],
      ["cl-b-01", "HELD"],
    ]);
    const claims = [
      { id: "cl-a-02", verdict: "verified" },
      { id: "cl-b-01", verdict: "blocked" }, // a lost row shows as blocked and scores as HELD
      { id: "cl-c-01", verdict: "blocked" }, // not scored
    ];
    expect(recordOf(landedOf(claims, table), points)).toEqual({ STANDS: 1, AMENDED: 0, OVERTURNED: 0, CHECKING: 0, pts: 3 });
  });

  it("writes points with a sign", () => {
    expect([signedPts(3), signedPts(0), signedPts(-6)]).toEqual(["+3", "0", "−6"]);
  });
});
