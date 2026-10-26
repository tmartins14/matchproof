import type { Beat, Claim, StreamMessage } from "@/contracts/types";
import type { ClaimRow } from "@/trials/data";

/** One line of a recorded fixture stream (scripts/record_fixtures.py). */
export interface RecordedLine {
  wall_ms: number;
  msg: StreamMessage;
}

/** What a cached claim row carries besides the row itself: the numbers the export tied to facts. */
export interface CachedRow {
  row: ClaimRow;
  numbers: Claim["numbers"];
}

export interface Timed {
  wall_ms: number;
  msg: StreamMessage;
}

/** The on-air time to use when a row has none (a lost row). */
export const DEFAULT_LATENCY_MS = 1500;
const NO_CLAIM_TEXT = "No claim aired";

const VERDICT = { STANDS: "verified", AMENDED: "rephrased", OVERTURNED: "blocked", HELD: "delayed" } as const;

export function parseNdjson(text: string): RecordedLine[] {
  return text
    .split("\n")
    .filter((line) => line.trim())
    .map((line) => JSON.parse(line) as RecordedLine);
}

/**
 * The recording's text from its bytes. The file is gzip, but a host that sees `Accept-Encoding` may add
 * its own `Content-Encoding: gzip` (Static Web Apps does), and then the browser has already decoded it.
 */
export async function decodeRecording(bytes: Uint8Array): Promise<string> {
  const gzip = bytes[0] === 0x1f && bytes[1] === 0x8b;
  if (!gzip) return new TextDecoder().decode(bytes);
  return new Response(new Blob([bytes as BlobPart]).stream().pipeThrough(new DecompressionStream("gzip"))).text();
}

/** Reads `/trials/streams/<fixture>.ndjson.gz`. */
export async function loadRecording(fixture: string, base = ""): Promise<RecordedLine[]> {
  const reply = await fetch(`${base}/trials/streams/${fixture}.ndjson.gz`);
  if (!reply.ok) throw new Error(`recording ${fixture}: ${reply.status}`);
  return parseNdjson(await decodeRecording(new Uint8Array(await reply.arrayBuffer())));
}

/** The claim as the Desk shows it: still `checking` on the draft, or settled in the row's verdict. A lost row is a blocked claim with its reason. */
export function claimOf({ row, numbers }: CachedRow, stage: "checking" | "settled"): Claim {
  const lost = row.lost !== null;
  const draft = row.draft_text || (lost ? NO_CLAIM_TEXT : row.text);
  const reason = row.reasons[0]?.slice(0, 400) ?? "";
  const final: Claim["verdict"] = lost ? "blocked" : (VERDICT[row.verdict] ?? "delayed");
  const kind = stage === "checking" ? "checking" : final;
  const changed = kind === "rephrased" || kind === "blocked";
  const claim: Claim = {
    id: row.id,
    beat_id: row.beat,
    lang: "en",
    // A blocked claim keeps the Narrator's draft wording for audit.
    text: kind === "blocked" || kind === "checking" ? draft : row.text,
    fact_ids: row.fact_ids,
    numbers,
    verdict: kind,
  };
  if (changed) {
    claim.draft_text = draft;
    claim.reason = reason;
  }
  return claim;
}

/** Every claim row of the candidate on a beat, in index order, scored or not. */
export function rowsOnBeat(rows: CachedRow[], beat: string): CachedRow[] {
  return rows.filter((r) => r.row.beat === beat);
}

/**
 * The recording with the candidate's claims injected: at each beat message, every claim row for that
 * beat arrives as `checking`, and its verdict follows `latency_ms` later. Injected messages are
 * numbered above the recording's last seq so nothing collides.
 */
export function buildTimeline(lines: RecordedLine[], rows: CachedRow[]): Timed[] {
  let seq = lines.reduce((top, l) => Math.max(top, l.msg.seq), -1);
  const out: Timed[] = [];
  for (const line of lines) {
    out.push(line);
    if (line.msg.type !== "beat") continue;
    const beat = line.msg.data as Beat;
    for (const cached of rowsOnBeat(rows, beat.id)) {
      const base = { t: line.msg.t };
      out.push({ wall_ms: line.wall_ms, msg: { seq: ++seq, type: "claim", ...base, data: claimOf(cached, "checking") } });
      const after = cached.row.latency_ms ?? DEFAULT_LATENCY_MS;
      out.push({ wall_ms: line.wall_ms + after, msg: { seq: ++seq, type: "verdict", ...base, data: claimOf(cached, "settled") } });
    }
  }
  // Array.sort is stable: equal times keep their order, so a claim stays after its beat.
  return out.sort((a, b) => a.wall_ms - b.wall_ms);
}

export interface Clock {
  now: () => number;
  request: (cb: () => void) => number;
  cancel: (id: number) => void;
}

export const browserClock: Clock = {
  now: () => performance.now(),
  request: (cb) => requestAnimationFrame(cb),
  cancel: (id) => cancelAnimationFrame(id),
};

/**
 * Dispatches a timeline at its recorded offsets from one loop: each frame sends every message that
 * has come due as a single batch, so the desk renders at most once per frame.
 */
export class CachedPlayer {
  private index = 0;
  private startedAt = 0;
  private frame: number | undefined;

  constructor(
    private readonly timeline: Timed[],
    private readonly onBatch: (batch: StreamMessage[]) => void,
    private readonly onDone: () => void,
    private readonly clock: Clock = browserClock,
  ) {}

  start(): void {
    this.startedAt = this.clock.now();
    this.frame = this.clock.request(this.tick);
  }

  stop(): void {
    if (this.frame !== undefined) this.clock.cancel(this.frame);
    this.frame = undefined;
  }

  private tick = (): void => {
    const elapsed = this.clock.now() - this.startedAt;
    const batch: StreamMessage[] = [];
    while (this.index < this.timeline.length && this.timeline[this.index]!.wall_ms <= elapsed) {
      batch.push(this.timeline[this.index]!.msg);
      this.index += 1;
    }
    if (batch.length > 0) this.onBatch(batch);
    if (this.index >= this.timeline.length) {
      this.frame = undefined;
      this.onDone();
      return;
    }
    this.frame = this.clock.request(this.tick);
  };
}
