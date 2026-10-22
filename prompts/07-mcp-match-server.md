# Build prompt 07 — MCP match server and capacity

**Mode:** code. **Budget:** about 2.5 hours. **Branch:** `feat/mcp-match`. **Depends on:** prompt 06 merged.

## Context

Read:
- `CLAUDE.md`
- `docs/ARCHITECTURE.md` (the agents table and "match-data MCP")
- `docs/adr/0002-foundry-and-agent-framework.md`
- `schemas/fact.schema.json`, `schemas/beat.schema.json`, `schemas/claim.schema.json`, `schemas/claim_graph.schema.json`
- `services/api/src/api/live.py` and `main.py`
- `packages/intel/src/intel/registry.py`

This task builds the agents' only door to match data. Thursday's Narrator and Checker read facts, events, freeze frames and beats through it and write claims through it. It's an MCP server, one of the named hero technologies, built with the official `mcp` Python SDK.

**Design decision: least privilege.**
- **Public, read-only:** the same server is mounted at `/mcp` over streamable HTTP. A judge can point any MCP client at the live URL and query a match. It has no write tools and is rate-limited.
- **Internal, read-write:** an in-process instance for the agent workflow, the only one with `put_claims`. It is never exposed over the network.

Record this in a new ADR, `docs/adr/0008-mcp-read-only-public-writes-internal.md`.

Before writing: restate the task back in eight lines or fewer. Include how one set of tool definitions produces both servers, and how a live match's state becomes visible to the server while it streams. Then wait for my go.

## Seam rules

- MCP tools return computed data only; no tool computes a new statistic. Facts come from the registry; nothing is formatted ad hoc.
- Every tool result validates against an existing schema, or a small output schema added in this PR. Run `make gen` if a schema changes.
- No secrets. The public endpoint has no write path, so it needs no key.

## Parts

1. **`mcp_match/store.py`: the match store.**
   - A `MatchStore` protocol and an in-memory implementation, keyed by `match_id`, holding: the brief, events seen so far, freeze frames by event id, the `FactRegistry`, beats, and claims by beat.
   - `live.py` registers each running match and updates it as the pipeline advances, so agents can query mid-match.
   - **Eviction:** least recently used, `MAX_MATCHES = 6`.
   - Blob persistence is Friday; keep the protocol small enough to back with Blob later.
2. **`mcp_match/server.py`: `build_server(store, writable: bool) -> FastMCP`.** Tools:
   - `get_brief(match_id)`
   - `get_fact(match_id, fact_id)`: the full fact, including display renderings and sources.
   - `find_facts(match_id, name_prefix=None, side=None, t_from=None, t_to=None, limit=50)`: maximum limit 200.
   - `get_events(match_id, t_from, t_to, types=None, limit=200)`
   - `get_freeze_frame(match_id, event_id)`: players' ids, sides and positions rounded to 0.1 m, plus the ball. Not the 5 Hz stream.
   - `list_beats(match_id, after_t=None)`
   - `get_beat_bundle(match_id, beat_id)`: the beat plus every fact it cites, in one call. This is what the Narrator receives.
   - `put_claims(match_id, beat_id, claims)`, **only when `writable`**: each claim is validated against `claim.schema.json`; it rejects claims for unknown beats or citing unknown fact ids, and returns per-claim errors.

   Unknown match, fact, beat or event ids return a clear MCP tool error, never an exception trace. Tool descriptions are short and plain (`docs/VOICE.md` applies; they are read by models and by judges in the inspector).
3. **Mounting:** in `services/api`, mount the read-only server at `/mcp` (streamable HTTP), limited to `MCP_RPM_PER_CLIENT = 60` requests per minute per client IP. Expose `get_internal_server(store)` for Thursday's workflow.
4. **Capacity** (approved Oct 21):
   - In `infra/modules/containerapp.bicep`, raise the API container to **1 vCPU and 2 GiB**.
   - In `live.py`, add `MAX_LIVE_STREAMS = 3` per replica. A further stream gets HTTP 503 with `Retry-After: 30` and a JSON body `{"fallback": "cached"}`. The cached replay that answers it comes Sunday.
   - Update `docs/DEPLOY.md` with the new size.
5. **Docs:** add an MCP section to `docs/ARCHITECTURE.md` (tools table, public versus internal) and a "Connect with an MCP client" snippet to `docs/DEPLOY.md`.

## Tests

- Call each tool through the SDK's in-memory client on a finished `red_card_flip` seed 3 match. Results validate against their schemas.
- `get_beat_bundle` for the red-card follow-up beat returns every cited fact, including `back_line_change` for the 10-man team.
- The read-only server does not list `put_claims`. The internal one does, and it accepts a valid claim, rejects one citing an unknown fact id, and rejects one for an unknown beat.
- **Mid-match visibility:** while a stream is half-way through (fake pacer), `list_beats` returns only beats detected so far, and `get_events` returns nothing past the playback lookahead.
- **Limits and errors:** `find_facts` caps at 200; unknown ids give tool errors; the 61st call in a minute from one client is refused; a 4th concurrent stream gets 503 with the fallback body.
- **Eviction:** a 7th match evicts the least recently used one.

## Verification signal (show the output)

1. `make lint typecheck test` exits 0; CI green.
2. A tool list and two calls (`list_beats`, then `get_beat_bundle` on the red-card follow-up) against `make api-dev`, from the SDK client or `npx @modelcontextprotocol/inspector`.
3. The Bicep diff for the container size.

## Omissions list (required in the PR)

Unverified behaviour, especially the public endpoint behind Container Apps ingress, and anything about rate limits that was only tested locally.

## Out of scope

Agents and Agent Framework wiring (Thursday), Blob persistence (Friday), the cached replay (Sunday), UI, and running `azd up` (Tyler runs it after merge).
