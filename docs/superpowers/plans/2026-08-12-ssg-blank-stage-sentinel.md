# SSG Blank Stage Sentinel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve valid SSG shipping-direction orders, enrich them through shipping-number quick searches using official field names, then load the recovered order into SQL Server.

**Architecture:** Use the shipping-direction feed for base rows, then query non-delivery and delivery-completed feeds once per unique shipping number. Normalize blank sentinels, merge official enrichment fields by the deployed four-part identity, and keep database persistence unchanged.

**Tech Stack:** Python 3.12, `unittest`, `requests`, SQL Server via `pymssql`.

## Global Constraints

- Do not print API credentials, response bodies, personal data, or raw order payloads.
- Do not change schemas or adapters for other channels.
- Treat only whitespace-only strings as empty sentinels; continue rejecting nonblank strings.
- Do not call `listWarehouseOut`; it is an outbound-processing target list rather than a completion feed.
- Leave `DeliveryTrackingStatusAt` null because no approved response field supports it.
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

### Task 2: Enrich by shipping-number quick search

**Files:**
- Modify: `tests/test_ssg.py`
- Modify: `src/hmr_order_collection/channels/ssg.py`

**Interfaces:**
- Consumes: base records keyed by `(ordNo, ordItemSeq, shppNo, shppSeq)` and quick-search responses from `listNonDelivery` and `listDeliveryEnd`.
- Produces: merged records using official `whoutDt`, `delicoVenId`, `wblNo`, `shppDt`, and `lastShppProgStatDtlCd` fields.

- [ ] **Step 1: Write failing quick-search and mapping tests**

Use synthetic official response shapes to assert that each unique `shppNo` is sent as `{"commType": "02", "commValue": shpp_no}` to both enrichment endpoints, `listWarehouseOut` is not called, and the official response fields populate the deployed columns.

- [ ] **Step 2: Verify the new tests fail**

Run the named SSG quick-search and mapping tests with `python -m unittest ... -v`.

Expected: failures show the existing period request, obsolete endpoint call, and missing official-field mappings.

- [ ] **Step 3: Implement quick-search enrichment**

Collect base rows, issue two quick searches per unique shipping number, accept the official `nonDeliverys` and `deliveryEnds` keys, merge matching identities, and map the approved fields. Preserve failure behavior for nonblank malformed values and non-success result codes.

- [ ] **Step 4: Run focused and full tests**

Run: `python -m unittest tests.test_ssg -v`

Run: `python -m unittest discover -s tests -v`

Expected: all tests pass with no warnings, errors, or failures.

- [ ] **Step 5: Commit the enrichment correction**

```bash
git add -- tests/test_ssg.py src/hmr_order_collection/channels/ssg.py
git commit -m "fix: enrich SSG orders by shipping number"
```

### Task 3: Reload and verify SSG

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
