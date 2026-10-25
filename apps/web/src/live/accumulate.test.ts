import { describe, expect, it } from "vitest";
import type { Beat, Claim, Status, StreamMessage } from "@/contracts/types";
import { copy } from "@/desk/copy";
import { emptyDesk, type DeskData } from "@/desk/deskData";
import { fixture } from "@/desk/fixture";
import { buildModel } from "@/desk/model";
import type { ReviewState } from "@/desk/reviewParams";
import { buildMomentum, buildStats } from "@/desk/statsModel";
import { accumulate } from "./accumulate";
import { recordedStream } from "./recorded";

const stream = recordedStream();
const fresh = (): DeskData => emptyDesk(fixture.brief, "live");
const played = stream.reduce(accumulate, fresh());
const statuses = stream.filter((m) => m.type === "status").map((m) => ({ seq: m.seq, ...(m.data as Status) }));
const state: ReviewState = { lang: "en", mode: "analyst", setupOpen: false };

describe("the recorded stream through the reducer", () => {
  it("is real API output with every kind of message", () => {
    expect(new Set(stream.map((m) => m.type))).toEqual(new Set(["status", "event", "frame", "fact", "beat"]));
    expect(stream.map((m) => m.seq)).toEqual([...stream.map((m) => m.seq)].sort((a, b) => a - b));
  });

  it("collects every beat, with the highlight the pipeline set", () => {
    const beats = stream.filter((m) => m.type === "beat").map((m) => m.data as Beat);
    expect(played.beats.map((b) => b.id)).toEqual(beats.map((b) => b.id));
    expect(beats.length).toBeGreaterThan(0);
    for (const beat of beats) expect(played.highlights[beat.id]).toEqual(beat.highlight);
    expect(beats.some((b) => b.highlight)).toBe(true);
  });

  it("follows the score the server sent after each goal, and full time carries it", () => {
    const scores = statuses.filter((s) => s.state === "score");
    expect(scores.length).toBeGreaterThanOrEqual(2);
    let d = fresh();
    for (const m of stream) {
      d = accumulate(d, m);
      const s = m.type === "status" ? (m.data as Status) : undefined;
      if (s?.state === "score" || s?.state === "full_time") expect(d.score).toEqual(s.score);
    }
    const fullTime = statuses.find((s) => s.state === "full_time");
    expect(fullTime?.score).toEqual(scores.at(-1)?.score);
    expect(played.score).toEqual(fullTime?.score);
    expect(played.phase).toBe("full_time");
  });

  it("stores the freeze frame that follows each freeze status", () => {
    const freezes = statuses.filter((s) => s.state === "freeze");
    expect(freezes.length).toBeGreaterThan(0);
    for (const s of freezes) {
      const frame = played.frames[s.event_id ?? ""];
      expect(frame, s.event_id).toBeDefined();
      expect(frame?.freeze_frame_of).toBe(s.event_id);
    }
  });

  it("returns to focus once play resumes after a freeze", () => {
    const at = stream.findIndex((m) => m.type === "status" && (m.data as Status).state === "freeze");
    const phases = [];
    let d = stream.slice(0, at + 1).reduce(accumulate, fresh());
    phases.push(d.phase);
    let frames = 0; // the first frame is the freeze frame itself; the next one is play resuming
    for (const m of stream.slice(at + 1)) {
      d = accumulate(d, m);
      if (m.type === "frame" && ++frames === 2) {
        phases.push(d.phase);
        break;
      }
    }
    expect(phases).toEqual(["freeze", "focus"]);
  });

  it("counts messages received and keeps the latest five events for the ticker", () => {
    expect(played.counts.events).toBe(stream.filter((m) => m.type === "event").length);
    expect(played.counts.facts).toBe(new Set(stream.filter((m) => m.type === "fact").map((m) => (m.data as { id: string }).id)).size);
    expect(played.ticker_event_ids).toHaveLength(5);
    expect(played.liveFrame).toBe(stream.filter((m) => m.type === "frame").at(-1)?.data);
  });

  it("indexes running totals and momentum by name, so the stats and the strip fill in", () => {
    const stats = buildStats(played, played.clock, "en", copy.en);
    expect(stats?.rows.length).toBe(4);
    expect(played.running.length).toBeGreaterThan(0);
    expect(played.running.map((r) => r.minute)).toEqual([...played.running.map((r) => r.minute)].sort((a, b) => a - b));
    expect(played.momentum.filter(Boolean).length).toBeGreaterThan(0);
    expect(buildMomentum(played, played.clock).length).toBeGreaterThan(0);
  });
});

const claimMessage = (seq: number, type: "claim" | "verdict", claim: Claim): StreamMessage => ({ seq, type, t: 4300, data: claim });

describe("claims: the last message per claim wins", () => {
  const real = fixture.claims.find((c) => c.verdict === "rephrased")!;
  const base = (): DeskData => ({ ...fresh(), phase: "live" });

  it("replaces a checking claim with its verdict, in place", () => {
    const checking: Claim = { ...real, verdict: "checking", text: real.draft_text ?? real.text, draft_text: undefined };
    const d = [claimMessage(1, "claim", checking), claimMessage(2, "verdict", real)].reduce(accumulate, base());
    expect(d.claims).toHaveLength(1);
    expect(d.claims[0]).toEqual(real);
  });

  it("takes the correction's text and keeps the first draft", () => {
    const other = fixture.claims.find((c) => c.verdict === "verified")!;
    const corrected: Claim = { ...other, verdict: "rephrased", text: "A softer wording.", reason: "overclaim", correction: { at_t: 4400, previous_text: other.text, reason: "overclaim", by: ["auditor", "judge"] } };
    const withDraft: Claim = { ...other, draft_text: "The Narrator's first wording." };
    const d = [claimMessage(1, "claim", withDraft), claimMessage(2, "verdict", corrected)].reduce(accumulate, base());
    expect(d.claims).toHaveLength(1);
    expect(d.claims[0]?.text).toBe("A softer wording.");
    expect(d.claims[0]?.draft_text).toBe("The Narrator's first wording.");
    expect(d.claims[0]?.correction?.previous_text).toBe(other.text);
  });
});

describe("follow live", () => {
  it("shows the newest beat while following, and holds a pinned beat as new ones arrive", () => {
    const beats = stream.filter((m) => m.type === "beat");
    const first = beats[0]!;
    const rank = (m: StreamMessage): StreamMessage => ({ ...m, data: { ...(m.data as Beat), rank: 1 } });
    const upTo = (n: number): DeskData => stream.slice(0, stream.indexOf(beats[n]!) + 1).map((m) => (m.type === "beat" ? rank(m) : m)).reduce(accumulate, fresh());
    const following = buildModel(upTo(beats.length - 1), state);
    expect(following.selectedBeat?.id).toBe((beats.at(-1)!.data as Beat).id);
    const pinned = buildModel(upTo(beats.length - 1), { ...state, beat: (first.data as Beat).id });
    expect(pinned.selectedBeat?.id).toBe((first.data as Beat).id);
  });

  it("leaves a beat the Producer did not rank off the feed until it has a claim", () => {
    const d = stream.reduce(accumulate, fresh());
    expect(buildModel(d, state).feed).toHaveLength(0);
  });
});
