import type { Beat, Claim } from "@/contracts/types";
import type { DeskFixture } from "./fixture";
import type { Mode, ReviewState, StampState } from "./reviewParams";

export type Verdict = StampState;

export interface ClaimView {
  claim: Claim;
  verdict: Verdict;
  selected: boolean;
}

export interface BeatView {
  beat: Beat;
  headlineKey: string;
  verdict: Verdict;
  claims: ClaimView[];
  /** Claims the checker overturned in this beat, whether or not the mode shows them. */
  removed: number;
  /** Every claim verdict in the beat, shown or not. */
  verdicts: Verdict[];
  selected: boolean;
}

export interface DeskModel {
  clock: number;
  minute: number;
  revealed: Beat[];
  latest: Beat | undefined;
  selectedBeat: Beat | undefined;
  selectedClaim: ClaimView | undefined;
  feed: BeatView[];
}

/** The verdict a beat row shows, from the verdicts of the claims shown in it. */
export function beatVerdict(verdicts: Verdict[]): Verdict {
  if (verdicts.includes("checking")) return "checking";
  if (verdicts.includes("delayed")) return "delayed";
  if (verdicts.every((v) => v === "verified")) return "verified";
  if (verdicts.every((v) => v === "blocked")) return "blocked";
  return "rephrased";
}

function showsBlocked(mode: Mode): boolean {
  return mode !== "fan";
}

export function buildModel(fx: DeskFixture, state: ReviewState): DeskModel {
  const clock = fx.snapshot.t;
  const revealed = fx.beats.filter((b) => b.t_detect <= clock);
  const latest = revealed.at(-1);
  const byId = new Map(fx.beats.map((b) => [b.id, b]));
  const requested = state.beat ? byId.get(state.beat) : undefined;
  const selectedBeat = requested ?? latest;

  const claimsOf = (beat: Beat): Claim[] => fx.claims.filter((c) => c.beat_id === beat.id);
  const wanted =
    state.claim ?? (selectedBeat ? claimsOf(selectedBeat).find((c) => showsBlocked(state.mode) || c.verdict !== "blocked")?.id : undefined);

  const verdictOf = (claim: Claim, beat: Beat): Verdict => {
    if (state.stamp && claim.id === wanted) return state.stamp;
    return beat.id === latest?.id ? "checking" : claim.verdict;
  };

  const feed = [...revealed].reverse().map((beat): BeatView => {
    const all = claimsOf(beat).map((claim) => ({ claim, verdict: verdictOf(claim, beat), selected: claim.id === wanted }));
    const shown = all.filter((c) => showsBlocked(state.mode) || c.verdict !== "blocked");
    const removed = all.filter((c) => c.verdict === "blocked").length;
    return {
      beat,
      headlineKey: beat.kind,
      verdict: beatVerdict(all.map((c) => c.verdict)),
      claims: shown,
      removed,
      verdicts: all.map((c) => c.verdict),
      selected: beat.id === selectedBeat?.id,
    };
  });

  const selectedRow = feed.find((row) => row.selected);
  const selectedClaim = selectedRow?.claims.find((c) => c.selected) ?? selectedRow?.claims[0];
  return { clock, minute: fx.snapshot.minute, revealed, latest, selectedBeat, selectedClaim, feed };
}
