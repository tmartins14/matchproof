# ADR 0008: Public MCP is read-only; writes are in process only

**Status:** accepted, 2026-10-21

## Context

All agents reach match data through one MCP server (`docs/ARCHITECTURE.md`). The MCP server is also a named hero technology, and judges may test the live URL until Nov 10. A judge should be able to point any MCP client at the deployed API and query a match. The same tools also need a write path: the Narrator's claims go through `put_claims` so every handoff is traced.

## Decision

- One function, `build_server(store, writable)`, defines every tool. The read tools are always registered; `put_claims` is registered only when `writable` is true. One definition keeps the two servers from drifting apart.
- **Public:** `writable=False`, mounted at `/mcp` over streamable HTTP, stateless, with no key because it has no write path. It is limited to 60 requests per minute per client address and checks the `Host` header against `MCP_ALLOWED_HOSTS`.
- **Internal:** `writable=True`, returned by `get_internal_server(store)` for the agent workflow to use in process. No route reaches it.
- Both read the same `MatchStore`. A running match is registered when its stream starts and filled in as the pipeline advances, so agents can query it mid-match.
- Tools return stored or registry data only. No tool computes a statistic.

## Alternatives rejected

- **One server with an API key for writes:** puts a secret in the judges' path and in config, and one mistake exposes writes.
- **Two separately written servers:** their read tools would drift.
- **No public MCP:** loses the easiest way for a judge to see the hero technology.

## Consequences

- A public client can read any match in the store, including facts and beats not yet shown to viewers, up to the playback lookahead. Nothing it can read is secret.
- The rate limit is per address in one replica's memory. Behind several replicas the effective limit is higher.
- The SDK is pinned to `mcp<2`. Version 2 renames `FastMCP` and changes other APIs; moving to it is its own task.
- Blob persistence (Friday) replaces `InMemoryMatchStore` and keeps the `MatchStore` protocol.
