import type { StreamMessage } from "@/contracts/types";
import { failureOf, type Failure } from "./api";

export interface StreamHandlers {
  onMessage: (message: StreamMessage) => void;
  /** The server refused the stream (429, 503) or could not be reached. */
  onRefused: (reason: Failure) => void;
  /** The stream ended or broke after it opened. */
  onEnd: () => void;
}

/** Splits received text into complete SSE blocks and the unfinished rest. */
export function splitBlocks(buffer: string): { blocks: string[]; rest: string } {
  const parts = buffer.replace(/\r\n/g, "\n").split("\n\n");
  return { blocks: parts.slice(0, -1), rest: parts.at(-1) ?? "" };
}

/** The message in one SSE block, or undefined for a comment line such as the keep-alive. */
export function messageOf(block: string): StreamMessage | undefined {
  const data = block
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trimStart())
    .join("\n");
  return data ? (JSON.parse(data) as StreamMessage) : undefined;
}

/**
 * Opens the stream and returns a function that closes it. It reads the response itself rather than
 * through EventSource, because EventSource hides the status of a refused request and the desk has to
 * tell a full replica (503) or a rate limit (429) from a dropped connection. It never reconnects:
 * a resumed stream cannot replay the agents' messages, so the desk would drift from the match.
 */
export function openStream(url: string, handlers: StreamHandlers): () => void {
  const abort = new AbortController();
  let opened = false;
  void (async () => {
    try {
      const reply = await fetch(url, { signal: abort.signal, headers: { Accept: "text/event-stream" } });
      if (!reply.ok || !reply.body) {
        handlers.onRefused(failureOf(reply.status));
        return;
      }
      opened = true;
      const reader = reply.body.pipeThrough(new TextDecoderStream()).getReader();
      let buffer = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        const { blocks, rest } = splitBlocks(buffer + value);
        buffer = rest;
        for (const block of blocks) {
          const message = messageOf(block);
          if (message) handlers.onMessage(message);
        }
      }
      handlers.onEnd();
    } catch {
      if (abort.signal.aborted) return;
      if (opened) handlers.onEnd();
      else handlers.onRefused("unreachable");
    }
  })();
  return () => abort.abort();
}
