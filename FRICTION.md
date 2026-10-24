# FRICTION

Log friction here; don't fix it live. Three hits on the same thing earns a fix.

| Date | Friction | Count |
| --- | --- | --- |
| 2026-10-24 | `test_consensus.py::test_a_rewrite_that_fails_the_check_blocks_the_claim_with_its_correction` failed on GitHub runners and kept main red since PR 24 (the correction was stored but `sent` was empty). Cause: `run_live` sent `full_time` and closed the stream while an audit or correction was still running, and the tests only lined up by polling `ledger.pending` with sleep counts, which a slow runner outran. Fix: `run_live` holds `full_time` while `ledger.pending > 0` (up to `FULL_TIME_HOLD_S`, 30 s) and streams what lands; the tests wait on the correction itself (an `asyncio.Event` from the correction listener, with a timeout and message). It did not reproduce locally (12 of 12 passed under CPU load before the fix); the regression test releases the audits at the last tick and fails without the hold. May be the same as the unidentified local `pytest` failure logged on feat/desk-static. | 1 |
