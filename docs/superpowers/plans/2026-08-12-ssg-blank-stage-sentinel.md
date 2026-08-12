# SSG Blank Stage Sentinel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve valid SSG shipping-direction orders when a follow-up stage returns its empty result as a blank-string list element, then load the recovered order into SQL Server.

**Architecture:** Keep the existing four-API orchestration and normalize only blank strings at the `_stage_rows` response boundary. Malformed nonblank values continue to fail closed. Database persistence remains unchanged.

**Tech Stack:** Python 3.12, `unittest`, `requests`, SQL Server via `pymssql`.

## Global Constraints

- Do not print API credentials, response bodies, personal data, or raw order payloads.
- Do not change schemas or adapters for other channels.
- Treat only whitespace-only strings as empty sentinels; continue rejecting nonblank strings.
- Use the inclusive 180-day SSG window ending 2026-08-12 for the operational reload.

---

### Task 1: Accept blank follow-up-stage sentinels

**Files:**
- Modify: `tests/test_ssg.py`
- Modify: `src/hmr_order_collection/channels/ssg.py`

**Interfaces:**
- Consumes: `_stage_rows(value: Any, name: str) -> list[dict[str, Any]]`
- Produces: A stage-row list that excludes whitespace-only string sentinels while retaining dictionaries.

- [ ] **Step 1: Write the failing regression test**

Add a test that routes a normal `shppDirections` response, `{"resultCode": "00", "warehouseOuts": [""]}`, and successful empty responses for the remaining stages. Assert that `list(adapter.fetch(...))` returns the base shipping-direction record rather than raising `ValueError`.

- [ ] **Step 2: Verify the test fails for the production defect**

Run: `python -m unittest tests.test_ssg.SsgAdapterTests.test_fetch_treats_blank_follow_up_stage_sentinel_as_empty -v`

Expected: FAIL with `ValueError: SSG warehouseOuts list was malformed`.

- [ ] **Step 3: Implement the minimal normalization**

Change `_stage_rows` to skip elements satisfying `isinstance(row, str) and not row.strip()` before validating that all remaining elements are dictionaries.

- [ ] **Step 4: Verify focused and full tests**

Run: `python -m unittest tests.test_ssg -v`

Expected: all SSG tests pass.

Run: `python -m unittest discover -s tests -v`

Expected: all project tests pass with zero failures and errors.

- [ ] **Step 5: Commit the regression fix**

```bash
git add -- tests/test_ssg.py src/hmr_order_collection/channels/ssg.py
git commit -m "fix: accept empty SSG follow-up stage sentinel"
```

### Task 2: Reload and verify SSG

**Files:**
- No source files modified.

**Interfaces:**
- Consumes: `python -m hmr_order_collection.cli collect --channel ssg ... --write-db`
- Produces: Count-only collection summary and persisted `dbo.SSG_ORDER_ITEM` history row.

- [ ] **Step 1: Perform a count-only dry run**

Run the SSG collector from `2026-02-14` through `2026-08-12` with `--dry-run`.

Expected: status `ok`, four pages fetched, and at least one record.

- [ ] **Step 2: Persist the same verified response**

Run the identical collection window with `--write-db`.

Expected: status `ok` and the count-only summary reports the insert/change/skip outcome.

- [ ] **Step 3: Verify database state**

Query `dbo.SSG_ORDER_ITEM` for `COUNT_BIG(*)`, latest-row count, and `MAX(CollectedAt)`.

Expected: at least one total row, exactly one latest row for each identity, and a non-null collection timestamp from this run.
