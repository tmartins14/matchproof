# Build prompt 10 — Composer, custom moments and match storage

**Mode:** code. **Budget:** about 2.5 hours. **Branch:** `feat/composer-storage`. **Depends on:** PR #21 merged.

## Context

Read:
- `CLAUDE.md`, `docs/VOICE.md`
- `docs/SPEC.md` (item 1, custom moments), `docs/PLAN.md` (Friday and Sunday rows), `docs/adr/0004-tactics-canonical-input.md`, `docs/adr/0008-mcp-read-only-public-writes-internal.md`
- `schemas/match_brief.schema.json` (`storyline`, `planted_beats`), `schemas/claim_graph.schema.json`
- `packages/sim/src/sim/brief.py`
- `packages/mcp_match/src/mcp_match/store.py`
- `services/api/src/api/main.py`
- `infra/modules/storage.bicep`, `infra/modules/identity.bicep`

This task completes the input side and makes matches survive restarts:

1. **Custom moments.** A user (or the Composer) can plant their own moments, such as "red card for Ashford at 30–35′", not just pick one of four storylines. It turns the tactics panel into a scenario harness.
2. **Composer agent.** It turns a free-text brief into validated tactics plus planted moments. Randomize stays in code.
3. **Match storage.** Finished matches are saved (brief, events, facts, beats, claims, audit, frames) and reloaded on demand. Sunday's cached replay and judges testing until Nov 10 depend on this.

Before writing: restate the task back in ten lines or fewer. Include the validation rules for custom moments, how the Composer's output is checked before it reaches the generator, and the store layout. Then wait for my go.

## Seam rules

- Tactics are the canonical generator input (ADR 0004). The Composer proposes; code validates. Nothing the model returns reaches the generator without passing the same validator a hand-written brief passes.
- Brief text is still produced from tactics by the existing template, never by a model.
- Storage uses managed identity only. No connection strings or keys.

## Parts

1. **Custom storyline and validation (`sim/brief.py`, schema).**
   - Add `custom` to the storyline id enum and run `make gen`.
   - `validate_planted(beats) -> list[str]` returns plain-English errors:
     - at most 6 moments;
     - each window inside 0–95 with `minute_from` before `minute_to`;
     - at most one red card per side;
     - no two goals for the same side whose windows can't fit a goal sequence apart (at least 2 minutes);
     - a penalty counts as a goal.
   - **Final score:** derived from planted goals; nothing else scores (the existing v1 rule).
   - **Storyline text** for a `custom` brief comes from a template, for example "Custom: Ashford red card 30–35′; Rivermouth goal 70–80′".
   - `make_brief` accepts custom beats.
   - **Test:** for seeds 1–20 and 20 random valid custom sets (events only, no frames, fast), every planted moment happens inside its window, and the final score matches.
2. **Randomize (`sim/brief.py`).** `random_brief(seed)` sets random formations and dials, plus either a preset storyline or 1–3 random valid custom moments, deterministic per seed. The API exposes it as `POST /matches/random`.
3. **Composer (`agents/composer.py`, prompt `agents/prompts/composer.v1.md`).**
   - **Input:** free text, for example "Ashford sit deep and hit on the break; Rivermouth press high; Ashford lose a man just before half-time and hang on".
   - **Output (structured):** per-team formation and the three dials (0 to 1), plus either a storyline id or custom planted moments.
   - The prompt explains each dial in football terms ("press: 0 drops off, 1 presses high") and the moment kinds and windows.
   - **Validation:** run `validate_planted` and the schema; on errors, retry once with them, then return the best valid partial with `warnings` (for example, dropping an impossible moment).
   - Returns `{brief, brief_text, warnings}`, where `brief_text` is the deterministic template applied to the result, so the UI can show the user what was understood.
   - Uses the `composer` role in `models.yaml` (`gpt-5-mini`).
4. **API.**
   - `POST /compose {text}` returns the composed result. Limited to `COMPOSE_RPM_PER_CLIENT = 6`, and it counts toward the daily token cap.
   - `POST /matches` accepts a full `MatchBrief`, including custom moments, and returns 422 with the validator's messages when invalid.
5. **Match storage (`mcp_match/store.py` and a new `mcp_match/persist.py`).**
   - A `MatchArchive` protocol with two implementations: `FileArchive` (local, `data/archive/`, the default for `make api-dev`) and `BlobArchive` (Azure, container `matches`, managed identity via `DefaultAzureCredential`, account from `AZURE_STORAGE_ACCOUNT`). Choose with `MATCH_ARCHIVE=file|blob`.
   - **Layout** per match under `<match_id>/`:
     - `brief.json`
     - `events.jsonl.gz`
     - `facts.jsonl.gz`
     - `beats.jsonl`
     - `claim_graph.json` (validated against `claim_graph.schema.json`)
     - `audit.json`
     - `producer_log.json`: the Producer's decisions and notes, as served by `/matches/{id}/producer-log`
     - `usage.json`: tokens per role and model for the match, plus cost if `prices.yaml` is set
     - `frames.jsonl.gz` (5 Hz)
     - `freeze.jsonl.gz`
     - `manifest.json` (written last; it lists the files, sizes, schema versions, git SHA and created time, passed in by the caller)
   - **Save** at full time, in a background task, so the stream isn't delayed.
   - **Load on demand:** when a match isn't in memory, the store (and so MCP, fact lookup, `/audit` and `/producer-log`) loads it from the archive. Least-recently-used eviction still applies to memory only.
   - `GET /matches` lists archived matches from their manifests: id, storyline, score, created time, claim counts. Sunday's cached-replay picker uses it.
   - **Bicep:** make sure the API's managed identity has **Storage Blob Data Contributor** on the account (add it if missing), and that the `matches` container exists. Set `MATCH_ARCHIVE=blob` on the container app.
6. **Docs:**
   - ARCHITECTURE: a storage section with the layout, plus the Composer in the agents table.
   - DEPLOY: how to list archived matches in Blob with `az storage blob list --auth-mode login`.
   - DATA.md: archived matches are synthetic and contain no personal data.

## Tests (CI, no model calls)

- **Validation:** each rule has a failing case with a clear message, plus a valid custom brief that passes. `POST /matches` returns 422 with those messages.
- **Generator with custom moments:** the 20-seed test above.
- **Randomize:** deterministic per seed, and always valid.
- **Composer with a fake model:**
  - valid output passes through;
  - invalid output retries once with the errors;
  - a second failure returns a valid partial with warnings;
  - the output never bypasses `validate_planted`.
- **Compose endpoint:** 429 on the 7th call in a minute; counts toward the cap.
- **Archive:**
  - a `FileArchive` round trip returns an identical match;
  - the manifest is written last, so a manifest with no files is never read;
  - after a short test match finishes, its claim graph validates;
  - an evicted match reloads from the archive through MCP `get_fact` and `/audit`.
- **Blob:** unit-test `BlobArchive` against a fake container client; no real Azure in CI.

## Verification signal (show the output)

1. `make lint typecheck test` exits 0; CI green.
2. **Tonight, real models:** three `POST /compose` calls with their `brief_text` and warnings:
   - "Ashford sit deep and hit on the break, Rivermouth press high";
   - "Ashford lose a man just before half-time and hang on for a draw";
   - an impossible one, "Rivermouth score 7 in the first 5 minutes".
3. A custom match (red card for the away side at 30–35′) streamed locally, with the red-card follow-up beat and its claims.
4. **After `azd up`:** `GET /matches` on Azure listing that match, and the blob listing.

## Omissions list (required in the PR)

Composer behaviours seen only once; validation rules chosen by feel (the goal spacing); archive sizes per match.

## Out of scope

The UI, including the Moments editor and cached-replay picker (Sunday), the Localizer (Sunday), and movement v2 (Monday).
