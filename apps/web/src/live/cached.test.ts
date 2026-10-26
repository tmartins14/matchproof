import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { gunzipSync } from "node:zlib";
import { describe, expect, it } from "vitest";
import type { Beat, Claim } from "@/contracts/types";
import { emptyDesk } from "@/desk/deskData";
import { fixture } from "@/desk/fixture";
import type { ClaimRow } from "@/trials/data";
import { accumulate } from "./accumulate";
import { buildTimeline, CachedPlayer, claimOf, DEFAULT_LATENCY_MS, parseNdjson, type CachedRow, type Clock } from "./cached";

const claimSchema = JSON.parse(readFileSync(resolve(__dirname, "../../../../schemas/claim.schema.json"), "utf8")) as {
  required: string[];
  properties: Record<string, { enum?: string[]; maxLength?: number }>;
};

// A small slice of a real recording: everything up to the first two beats and a little after.
const all = parseNdjson(gunzipSync(readFileSync(resolve(__dirname, "../../public/trials/streams/fx-04.ndjson.gz"))).toString("utf8"));
const beatIdx = all.flatMap((l, i) => (l.msg.type === "beat" ? [i] : []));
const lines = all.slice(0, beatIdx[1]! + 40);
const beats = lines.filter((l) => l.msg.type === "beat").map((l) => l.msg.data as Beat);
const [first, second] = beats as [Beat, Beat];

const row = (extra: Partial<ClaimRow>): ClaimRow =>
  ({
    id: `cl-${first.id.slice(3)}-01`,
    fixture: "fx-04",
    beat: first.id,
    minute: 10,
    candidate: "gpt-5-mini",
    scored: true,
    lost: null,
    text: "Rivermouth lead 1–0.",
    draft_text: "Rivermouth lead 1–0.",
    verdict: "STANDS",
    reason_bucket: null,
    reasons: [],
    failed_span: null,
    corrected_span: null,
    fact_ids: ["fx-a"],
    checker: "1/1 numbers matched",
    auditor: "agree",
    referee_split: null,
    corrected_by_consensus: false,
    latency_ms: 4000,
    narrator_ms: 1200,
    tokens_in: 100,
    tokens_out: 20,
    ...extra,
  }) as ClaimRow;

const rows: CachedRow[] = [
  { row: row({}), numbers: [{ as_written: "1", fact_id: "fx-a" }] },
  { row: row({ id: `cl-${second.id.slice(3)}-01`, beat: second.id, verdict: "OVERTURNED", text: "Fixed wording.", draft_text: "Draft wording.", reasons: ["Judge (overclaim): too strong."], reason_bucket: "overclaim", latency_ms: 2500 }), numbers: [] },
];
const timeline = buildTimeline(lines, rows);

describe("the cached timeline", () => {
  it("brings each beat's claims after the beat, as checking", () => {
    for (const { row: r } of rows) {
      const beatAt = timeline.findIndex((t) => t.msg.type === "beat" && (t.msg.data as Beat).id === r.beat);
      const claimAt = timeline.findIndex((t) => t.msg.type === "claim" && (t.msg.data as Claim).id === r.id);
      expect(claimAt).toBeGreaterThan(beatAt);
      expect((timeline[claimAt]!.msg.data as Claim).verdict).toBe("checking");
      expect(timeline[claimAt]!.wall_ms).toBe(timeline[beatAt]!.wall_ms);
    }
  });

  it("sends each verdict latency_ms after its claim", () => {
    for (const { row: r } of rows) {
      const claim = timeline.find((t) => t.msg.type === "claim" && (t.msg.data as Claim).id === r.id)!;
      const verdict = timeline.find((t) => t.msg.type === "verdict" && (t.msg.data as Claim).id === r.id)!;
      expect(verdict.wall_ms - claim.wall_ms).toBe(r.latency_ms);
    }
  });

  it("uses 1500 ms when a row has no latency", () => {
    const t = buildTimeline(lines, [{ row: row({ latency_ms: null }), numbers: [] }]);
    const c = t.find((x) => x.msg.type === "claim")!;
    const v = t.find((x) => x.msg.type === "verdict")!;
    expect(v.wall_ms - c.wall_ms).toBe(DEFAULT_LATENCY_MS);
  });

  it("keeps wall_ms in order and numbers injected messages above the recording", () => {
    const walls = timeline.map((t) => t.wall_ms);
    expect(walls).toEqual([...walls].sort((a, b) => a - b));
    const top = Math.max(...lines.map((l) => l.msg.seq));
    const added = timeline.filter((t) => t.msg.type === "claim" || t.msg.type === "verdict").map((t) => t.msg.seq);
    expect(added.every((s) => s > top)).toBe(true);
    expect(new Set(timeline.map((t) => t.msg.seq)).size).toBe(timeline.length);
  });

  it("builds the same desk as the live path for the same messages", () => {
    const viaTimeline = timeline.map((t) => t.msg).reduce(accumulate, emptyDesk(fixture.brief, "live"));
    // What the live path does with the verdicts: the last message per claim wins.
    const live = emptyDesk(fixture.brief, "live");
    for (const t of timeline) accumulate(live, t.msg);
    expect(viaTimeline.claims.map((c) => [c.id, c.verdict])).toEqual([
      [rows[0]!.row.id, "verified"],
      [rows[1]!.row.id, "blocked"],
    ]);
    expect(viaTimeline.beats.map((b) => b.id)).toEqual(beats.map((b) => b.id));
    expect(viaTimeline.claims).toEqual(live.claims);
    expect(viaTimeline.facts.length).toBe(live.facts.length);
    expect(viaTimeline.score).toEqual(live.score);
  });
});

describe("a cached claim", () => {
  it("validates as claim.schema.json in every stage", () => {
    const lost = row({ lost: "no_claim", verdict: "HELD", draft_text: "", text: "", fact_ids: [], reasons: ["The Narrator wrote no claim for this beat."] });
    const amended = row({ verdict: "AMENDED", text: "New.", draft_text: "Old.", reasons: ["Judge (wording): off."] });
    const held = row({ verdict: "HELD" });
    for (const r of [rows[0]!.row, rows[1]!.row, lost, amended, held]) {
      for (const stage of ["checking", "settled"] as const) {
        const c = claimOf({ row: r, numbers: [] }, stage) as unknown as Record<string, unknown>;
        for (const key of claimSchema.required) expect(c, key).toHaveProperty(key);
        for (const key of Object.keys(c)) expect(claimSchema.properties, key).toHaveProperty(key);
        expect(claimSchema.properties.verdict!.enum).toContain(c.verdict);
        expect((c.text as string).length).toBeLessThanOrEqual(280);
        if (c.verdict === "rephrased" || c.verdict === "blocked") {
          expect(c.reason).toBeDefined();
          expect(c.draft_text).toBeDefined();
        }
        if (c.verdict === "verified" || c.verdict === "rephrased") expect((c.fact_ids as string[]).length).toBeGreaterThan(0);
      }
    }
  });

  it("maps the verdicts: STANDS verified, AMENDED rephrased, OVERTURNED blocked, HELD delayed", () => {
    const of = (verdict: ClaimRow["verdict"]) => claimOf({ row: row({ verdict }), numbers: [] }, "settled").verdict;
    expect([of("STANDS"), of("AMENDED"), of("OVERTURNED"), of("HELD")]).toEqual(["verified", "rephrased", "blocked", "delayed"]);
  });

  it("renders a lost row as blocked with its reason", () => {
    const lost = row({ lost: "no_claim", verdict: "HELD", draft_text: "", text: "", fact_ids: [], reasons: ["The Narrator wrote no claim for this beat."], latency_ms: null });
    const t = buildTimeline(lines, [{ row: lost, numbers: [] }]);
    const d = t.map((x) => x.msg).reduce(accumulate, emptyDesk(fixture.brief, "live"));
    expect(d.claims).toHaveLength(1);
    expect(d.claims[0]).toMatchObject({ verdict: "blocked", text: "No claim aired", reason: "The Narrator wrote no claim for this beat." });
  });

  it("keeps the draft on a blocked claim and the numbers the export gave", () => {
    const c = claimOf(rows[1]!, "settled");
    expect(c).toMatchObject({ verdict: "blocked", text: "Draft wording.", draft_text: "Draft wording.", reason: "Judge (overclaim): too strong." });
    expect(claimOf(rows[0]!, "settled").numbers).toEqual([{ as_written: "1", fact_id: "fx-a" }]);
  });
});

describe("the player", () => {
  function fakeClock() {
    let now = 0;
    let pending: (() => void) | undefined;
    const clock: Clock = {
      now: () => now,
      request: (cb) => {
        pending = cb;
        return 1;
      },
      cancel: () => {
        pending = undefined;
      },
    };
    return {
      clock,
      advance(ms: number) {
        now += ms;
        const cb = pending;
        pending = undefined;
        cb?.();
      },
      get waiting() {
        return pending !== undefined;
      },
    };
  }

  it("sends everything due in one batch per frame, and nothing early", () => {
    const f = fakeClock();
    const batches: number[] = [];
    let done = false;
    const small = [
      { wall_ms: 0, msg: timeline[0]!.msg },
      { wall_ms: 10, msg: timeline[1]!.msg },
      { wall_ms: 10, msg: timeline[2]!.msg },
      { wall_ms: 5000, msg: timeline[3]!.msg },
    ];
    new CachedPlayer(small, (b) => batches.push(b.length), () => (done = true), f.clock).start();
    f.advance(0);
    f.advance(15);
    f.advance(100);
    expect(batches).toEqual([1, 2]);
    f.advance(5000);
    expect(batches).toEqual([1, 2, 1]);
    expect(done).toBe(true);
    expect(f.waiting).toBe(false);
  });

  it("stop cancels the loop", () => {
    const f = fakeClock();
    const batches: number[] = [];
    const p = new CachedPlayer(timeline, (b) => batches.push(b.length), () => undefined, f.clock);
    p.start();
    p.stop();
    expect(f.waiting).toBe(false);
    f.advance(1_000_000);
    expect(batches).toEqual([]);
  });
});
