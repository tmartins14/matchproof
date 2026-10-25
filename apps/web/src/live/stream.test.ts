import { describe, expect, it } from "vitest";
import { failureOf } from "./api";
import { asSse, recordedStream } from "./recorded";
import { messageOf, splitBlocks } from "./stream";

describe("reading the stream", () => {
  it("rebuilds every recorded message from its SSE text, however the text is chunked", () => {
    const stream = recordedStream().slice(0, 200);
    const text = `: keep-alive\n\n${asSse(stream)}`;
    const read = [];
    let rest = "";
    for (let i = 0; i < text.length; i += 997) {
      const split = splitBlocks(rest + text.slice(i, i + 997));
      rest = split.rest;
      read.push(...split.blocks.map(messageOf).filter(Boolean));
    }
    expect(rest).toBe("");
    expect(read).toEqual(stream);
  });

  it("tells a refused request from a dropped one", () => {
    expect(failureOf(429)).toBe("rate_limit");
    expect(failureOf(503)).toBe("busy");
    expect(failureOf(500)).toBe("unreachable");
  });
});
