// Test helper: the recorded stream, as real API output (scripts/record_stream.py).
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { gunzipSync } from "node:zlib";
import type { StreamMessage } from "@/contracts/types";

export const RECORDED = resolve(__dirname, "../../fixtures/stream-short.ndjson.gz");

export function recordedStream(): StreamMessage[] {
  const text = gunzipSync(readFileSync(RECORDED)).toString("utf8");
  return text
    .split("\n")
    .filter((line) => line.trim())
    .map((line) => JSON.parse(line) as StreamMessage);
}

/** The stream as the server sends it: one SSE block per message. */
export function asSse(messages: StreamMessage[]): string {
  return messages.map((m) => `id: ${m.seq}\nevent: ${m.type}\ndata: ${JSON.stringify(m)}\n\n`).join("");
}
