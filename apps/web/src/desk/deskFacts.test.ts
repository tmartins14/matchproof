import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { EvidenceRail } from "@/components/desk/EvidenceRail";
import { MomentumStrip } from "@/components/desk/MomentumStrip";
import { SegmentedControl } from "@/components/desk/SegmentedControl";
import { copy } from "./copy";
import { fixture } from "./fixture";
import { buildModel } from "./model";
import { buildRail } from "./railModel";
import { buildMomentum, buildStats } from "./statsModel";

const SNAPSHOT_T = fixture.clock;
const factName = new Map(fixture.facts.map((f) => [f.id, f.name]));
const textOf = (html: string): string => html.replace(/<[^>]*>/g, " ");

describe("stats panel", () => {
  it("uses the to-date facts of the latest 5-minute mark at 71′", () => {
    expect(Math.floor(fixture.clock / 60)).toBe(71);
    const view = buildStats(fixture, SNAPSHOT_T, "en", copy.en)!;
    expect(view.window).toBe("Match · to 70′");
    expect(view.rows.map((r) => r.label)).toEqual(["Possession", "Shots", "Shots on target", "xG"]);
    for (const row of view.rows) {
      for (const id of row.factIds) expect(factName.get(id)).toMatch(/, to 70′\)$/);
    }
  });

  it("shows nothing before the first mark has closed", () => {
    expect(buildStats(fixture, 120, "en", copy.en)).toBeUndefined();
  });
});

describe("momentum strip", () => {
  const model = buildModel(fixture, { mode: "analyst", lang: "en", beat: undefined, claim: undefined, stamp: undefined, setupOpen: false });
  const render = (bars: ReturnType<typeof buildMomentum>): string =>
    renderToStaticMarkup(createElement(MomentumStrip, { copy: copy.en, bars, model, gridSeconds: 5400, headlineOf: (k: string) => k, onPick: () => undefined }));

  it("draws one bar per closed bucket, from the facts", () => {
    const closed = fixture.momentum.filter((id) => (fixture.facts.find((f) => f.id === id)?.scope?.t_to ?? Infinity) <= SNAPSHOT_T);
    const bars = buildMomentum(fixture, SNAPSHOT_T);
    expect(bars).toHaveLength(closed.length);
    expect(closed.length).toBe(14);
    expect(render(bars).match(/class="mp-moment-col"/g)).toHaveLength(closed.length);
  });

  it("scales by the largest value so far and puts the sign above or below the axis", () => {
    const bars = buildMomentum(fixture, SNAPSHOT_T);
    expect(Math.max(...bars.map((b) => Math.abs(b.scale)))).toBe(1);
    const html = render(bars);
    expect(bars.filter((b) => b.value > 0)).toHaveLength(html.match(/data-side="home"/g)?.length ?? 0);
    expect(bars.filter((b) => b.value < 0)).toHaveLength(html.match(/data-side="away"/g)?.length ?? 0);
    expect(bars.filter((b) => b.value === 0)).toHaveLength(html.match(/mp-moment-zero/g)?.length ?? 0);
  });
});

describe("evidence rail", () => {
  it("shows no raw seconds and no aggregate id as text, for every claim in both languages", () => {
    for (const lang of ["en", "es"] as const) {
      for (const claim of fixture.claims) {
        const view = { claim, verdict: claim.verdict, selected: true };
        const rail = buildRail(fixture, claim.fact_ids, claim.numbers.map((n) => n.fact_id), lang, copy[lang]);
        const text = textOf(renderToStaticMarkup(createElement(EvidenceRail, { copy: copy[lang], claim: view, rail })));
        // The machine name stays under each label (it is the proof); only the aggregates' descriptions are checked here.
        const rows = rail.events.filter((e) => !e.isEvent).map((e) => e.who);
        for (const who of rows) expect(who, claim.id).not.toMatch(/t\d+\.\d+|match time|1 Hz|samples|seconds before|\bev-\d|\bagg-/);
        expect(text, claim.id).not.toContain("agg-");
        expect(text, claim.id).not.toMatch(/match time/);
      }
    }
  });

  it("describes every aggregate source in the viewer's words, from the server's label", () => {
    const rows = fixture.claims.flatMap((claim) => buildRail(fixture, claim.fact_ids, claim.numbers.map((n) => n.fact_id), "en", copy.en).events.filter((e) => e.label === copy.en.rail.aggregate));
    expect(rows.length).toBeGreaterThan(0);
    for (const row of rows) expect(row.who).toMatch(/^(Play |Where )/);
  });

  it("puts the label first and the machine name beneath", () => {
    const claim = fixture.claims[0]!;
    const rail = buildRail(fixture, claim.fact_ids, [], "en", copy.en);
    expect(rail.factLines.length).toBeGreaterThan(0);
    for (const line of rail.factLines) expect(line.label).not.toBe(line.name);
  });
});

describe("segmented control cuts", () => {
  const cuts = (count: number): string[] => {
    const options = Array.from({ length: count }, (_, i) => ({ value: `v${i}`, label: `L${i}` }));
    const html = renderToStaticMarkup(createElement(SegmentedControl<string>, { label: "x", options, value: "v0", onChange: () => undefined }));
    return [...html.matchAll(/data-cut="(\w+)"/g)].map((m) => m[1]!);
  };

  it("takes cutStart, cutEnd for two items", () => expect(cuts(2)).toEqual(["cutStart", "cutEnd"]));
  it("keeps cut between the ends of three", () => expect(cuts(3)).toEqual(["cutStart", "cut", "cutEnd"]));
});
