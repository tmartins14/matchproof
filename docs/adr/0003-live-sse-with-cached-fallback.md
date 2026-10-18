# ADR 0003: Live streaming over SSE, cached replay as fallback

**Status:** accepted, 2026-10-18

## Context

The brief asks to ingest events "as they happen" and to be "responsive enough for live play". Judges may test the live URL at any time until Nov 10, and model calls cost money and can fail.

## Decision

- Live is the default path. The API streams generator output to the browser over Server-Sent Events at 1×, 3× or 6× match speed.
- Claims are narrated and checked asynchronously per beat and shown as Checking until a verdict arrives.
- Three pre-generated matches are stored as claim graphs and served as the cached replay.
- If a model call times out or the daily token cap trips, the run continues and the beat shows "verification delayed". If the API is unreachable, the site offers the cached replay.

## Alternatives rejected

- WebSockets: bidirectional channels are not needed; SSE is simpler and works through Container Apps ingress.
- Azure Event Hubs for the browser stream: adds a service without adding judged value. Revisit only for the Fabric audit stretch.

## Consequences

- A per-IP rate limit and a daily token cap are part of the API from day one.
- The SSE message types are part of the contract: `event`, `frame`, `fact`, `beat`, `claim`, `verdict`, `status`.
