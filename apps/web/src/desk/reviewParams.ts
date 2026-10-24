// Review aids for screenshots and design review. Prompt 12 replaces these with live state.
import type { Lang } from "./copy";

export type Mode = "fan" | "analyst" | "producer";
export type StampState = "checking" | "verified" | "rephrased" | "blocked" | "delayed";

export interface ReviewState {
  lang: Lang;
  mode: Mode;
  beat?: string;
  claim?: string;
  setupOpen: boolean;
  stamp?: StampState;
}

type RawParams = Record<string, string | string[] | undefined>;

function one(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

export function parseReviewParams(params: RawParams): ReviewState {
  const lang = one(params.lang) === "es" ? "es" : "en";
  const modeParam = one(params.mode);
  const mode: Mode = modeParam === "fan" || modeParam === "producer" ? modeParam : "analyst";
  const stampParam = one(params.stamp);
  const stamps: StampState[] = ["checking", "verified", "rephrased", "blocked", "delayed"];
  return {
    lang,
    mode,
    beat: one(params.beat),
    claim: one(params.claim),
    setupOpen: one(params.setup) === "open",
    stamp: stamps.find((s) => s === stampParam),
  };
}
