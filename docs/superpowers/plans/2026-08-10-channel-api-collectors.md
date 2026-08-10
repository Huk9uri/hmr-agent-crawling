# Channel API Collectors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build read-only API collectors for the seven authenticated sales channels and safely append one row per order item into the deployed SQL Server channel tables.

**Architecture:** A shared Python package owns configuration, retries, masking, payload hashing, collection-run metadata, and SQL Server history writes. Each channel adapter owns only authentication, maximum allowed date windows, pagination, response extraction, and mapping to its channel table. The CLI supports per-channel dry-run and explicit database-write modes so API responses can be inspected before insertion.

**Tech Stack:** Python 3.12, `requests`, `pymssql`, standard-library `unittest`, SQL Server 2017, environment variables from `.env`.

## Global Constraints

- Call read-only order APIs only; never confirm orders, dispatch shipments, cancel, return, exchange, or change channel state.
- Never print or persist API keys, access tokens, receiver names, phone numbers, addresses, email addresses, or customs identifiers.
- Mask sensitive fields recursively before JSON serialization and hashing.
- Use one `CollectionRunId` per channel execution and UTC `CollectedAt` values.
- Fetch every page until the documented continuation token is absent.
- Split requested periods into each API's maximum permitted window; never silently truncate.
- Write one row per order item and preserve history. If the latest `PayloadHash` is unchanged, skip insertion.
- When changed, update the previous latest row to `IsLatest = 0` and insert the new row with `IsLatest = 1` in one database transaction.
- A channel failure must not roll back already committed data from another channel; record the channel as failed and continue only when `--continue-on-error` is supplied.
- `.env`, raw response bodies, and token caches must remain Git-ignored.

## File Structure

```text
src/hmr_order_collection/
  __init__.py              package marker
  cli.py                   list, dry-run, and collect commands
  config.py                strict .env loading without secret logging
  http.py                  timeout, retry, rate-limit, and JSON/XML helpers
  masking.py               recursive PII masking and canonical JSON
  models.py                ChannelRecord and CollectionResult contracts
  database.py              pymssql connection and history upsert
  channels/
    __init__.py            adapter registry
    base.py                ChannelAdapter interface and date-window iterator
    naver.py               OAuth2, 24-hour changed-order paging, 300-ID details
    coupang.py              HMAC signing, status loops, 31-day windows, nextToken
    godomall.py             partner/user keys, Order_Search, lastOrder paging
    lotteon.py              API key, delivery-order and progress queries
    elevenst.py             openapikey XML order queries
    ssg.py                  Authorization key, 180-day shipping-direction query
    toss.py                 OAuth2 token, 31-day windows, nextCursor paging
tests/
  test_masking.py
  test_windows.py
  test_database.py
  test_naver.py
  test_coupang.py
  test_godomall.py
  test_lotteon.py
  test_elevenst.py
  test_ssg.py
  test_toss.py
  fixtures/                synthetic, masked API responses only
```

---

### Task 1: Shared contracts, configuration, masking, and HTTP behavior

**Files:**
- Create: `src/hmr_order_collection/config.py`
- Create: `src/hmr_order_collection/models.py`
- Create: `src/hmr_order_collection/masking.py`
- Create: `src/hmr_order_collection/http.py`
- Test: `tests/test_masking.py`

**Interfaces:**
- `load_config(path: Path) -> AppConfig`
- `mask_payload(value: object) -> object`
- `canonical_payload(value: object) -> tuple[str, bytes]`
- `ChannelRecord(identity: tuple, columns: dict, raw_json: str, payload_hash: bytes)`

- [ ] Write tests proving nested keys matching name, phone, tel, address, email, customs, token, secret, and key are replaced by `***`, while order and product identifiers remain unchanged.
- [ ] Run `python -m unittest tests.test_masking -v` and confirm the tests fail because the package does not exist.
- [ ] Implement strict `.env` parsing, immutable model dataclasses, recursive masking, stable sorted JSON, SHA-256 hashing, 10/60-second connect/read timeouts, bounded retry for 429 and 5xx, and response parsing that never logs bodies on errors.
- [ ] Run the masking tests and confirm they pass.
- [ ] Commit with `feat: add collector foundations`.

### Task 2: Date windows and SQL Server history writer

**Files:**
- Create: `src/hmr_order_collection/channels/base.py`
- Create: `src/hmr_order_collection/database.py`
- Test: `tests/test_windows.py`
- Test: `tests/test_database.py`

**Interfaces:**
- `iter_windows(start: date, end: date, maximum_days: int) -> Iterator[DateWindow]`
- `ChannelAdapter.fetch(window: DateWindow) -> Iterator[ChannelRecord]`
- `DatabaseWriter.write(channel: str, records: Iterable[ChannelRecord], run_id: UUID) -> WriteSummary`

- [ ] Write failing tests for inclusive 1-, 24-, 31-, and 180-day window boundaries and for unchanged, changed, and new payload decisions.
- [ ] Implement inclusive non-overlapping window generation and a whitelist-based table/identity mapping for all seven deployed tables.
- [ ] Implement parameterized `pymssql` statements. Lock the current latest identity row, compare `PayloadHash`, update `IsLatest`, and insert the new row in one transaction.
- [ ] Verify rollback on any row failure and verify no SQL identifier comes from API data.
- [ ] Commit with `feat: add collection history writer`.

### Task 3: Naver SmartStore and Coupang adapters

**Files:**
- Create: `src/hmr_order_collection/channels/naver.py`
- Create: `src/hmr_order_collection/channels/coupang.py`
- Test: `tests/test_naver.py`
- Test: `tests/test_coupang.py`

**Interfaces:**
- Naver uses OAuth2 client credentials, changed-order windows of 24 hours, `more.moreFrom` plus `more.moreSequence`, and detail batches of at most 300 product-order IDs.
- Coupang uses HMAC-SHA256 signing, all six order statuses, inclusive windows of at most 31 days, `maxPerPage=50`, and `nextToken` until absent.

- [ ] Add masked synthetic fixtures and failing tests for token acquisition, continuation paging, detail batching, all-status collection, and field mapping to `NAVER_SMARTSTORE_ORDER_ITEM` and `COUPANG_ORDER_ITEM`.
- [ ] Implement read-only requests and exact channel mappings.
- [ ] Verify repeated pages cannot create an infinite loop by tracking continuation tokens.
- [ ] Commit with `feat: add Naver and Coupang collectors`.

### Task 4: Godomall, LotteON, and 11st adapters

**Files:**
- Create: `src/hmr_order_collection/channels/godomall.py`
- Create: `src/hmr_order_collection/channels/lotteon.py`
- Create: `src/hmr_order_collection/channels/elevenst.py`
- Test: `tests/test_godomall.py`
- Test: `tests/test_lotteon.py`
- Test: `tests/test_elevenst.py`

**Interfaces:**
- Godomall calls `Order_Search.php`, follows `lastOrder`, and retains `orderChannelFl` so general, Naver Pay, and Payco orders remain distinguishable.
- LotteON calls both `SellerDeliveryOrdersSearch` and `SellerDeliveryProgressStateSearch`, joins responses by order and item identity, and performs no status-changing call.
- 11st calls the read-only order endpoints with `openapikey`, parses XML defensively, and maps one `orderProductNo` per row.

- [ ] Write failing fixture tests for paging, empty results, XML namespaces, Lotte delivery joins, and channel-specific field mappings.
- [ ] Implement each adapter with its verified endpoint and authentication headers.
- [ ] Treat a successful empty response as zero records, not an error.
- [ ] Commit with `feat: add Godomall LotteON and 11st collectors`.

### Task 5: SSG.COM and Toss Shopping adapters

**Files:**
- Create: `src/hmr_order_collection/channels/ssg.py`
- Create: `src/hmr_order_collection/channels/toss.py`
- Test: `tests/test_ssg.py`
- Test: `tests/test_toss.py`

**Interfaces:**
- SSG calls `/api/pd/1/listShppDirection.ssg` with `perdType=02` in windows of at most 180 days and maps each `(ordNo, ordItemSeq, shppNo, shppSeq)` row.
- Toss obtains an OAuth2 client-credentials token, queries windows of at most 31 days with `limit=50`, and follows `success.nextCursor` until null.

- [ ] Write failing tests for SSG result codes, Toss `resultType`, token refresh, continuation paging, privacy masking, and exact table mappings.
- [ ] Implement both read-only adapters and reject business-level failures even when Toss returns HTTP 200.
- [ ] Commit with `feat: add SSG and Toss collectors`.

### Task 6: CLI, dry run, maximum-range backfill, and operational verification

**Files:**
- Create: `src/hmr_order_collection/cli.py`
- Create: `src/hmr_order_collection/channels/__init__.py`
- Create: `tests/test_cli.py`
- Modify: `.gitignore`
- Modify: `docs/channel-order-tables.md`

**Interfaces:**
- `python -m hmr_order_collection.cli list`
- `python -m hmr_order_collection.cli collect --channel naver --from YYYY-MM-DD --to YYYY-MM-DD --dry-run`
- `python -m hmr_order_collection.cli collect-all --to 2026-08-10 --maximum-window --write-db`

- [ ] Write failing CLI tests proving database writes require `--write-db`, dates cannot be in the future, unknown channels fail, and summaries contain counts but no secrets or PII.
- [ ] Implement the adapter registry, channel-by-channel execution, JSON summary output, and exit codes.
- [ ] Run the full `unittest` suite and `git diff --check`.
- [ ] Execute dry runs first against every authenticated channel. Record per-channel windows, pages, records, and masked failures.
- [ ] Run database writes only for channels whose dry run succeeds; verify inserted/skipped/changed counts and the one-latest-row invariant.
- [ ] Query SQL Server for per-channel row counts and verify no unmasked PII keys exist in `RawJson` samples.
- [ ] Commit with `feat: collect channel orders into SQL Server`.

## Initial Backfill Windows

The first production run uses the maximum single-request window currently verified for each endpoint, ending on 2026-08-10. The CLI still splits and paginates every response.

| Channel | Initial window policy |
|---|---|
| Naver SmartStore | 24-hour changed-order slices; continue with `moreFrom` and `moreSequence` |
| Coupang | Previous 31 calendar days for every order status; `nextToken` paging |
| Godomall | Largest accepted Order_Search period determined by a dry-run boundary probe; `lastOrder` paging |
| LotteON | Largest accepted delivery-order period determined by a dry-run boundary probe; query order and progress APIs |
| 11st | Largest accepted order period determined by a dry-run boundary probe; never call confirmation or dispatch APIs |
| SSG.COM | Previous 180 calendar days by order-completion date |
| Toss Shopping | Previous 31 calendar days, all statuses, `limit=50`, `nextCursor` paging |

Boundary probes start with the documented or previously verified range and reduce only when the API returns an explicit invalid-period response. They never mutate channel state and never infer success from HTTP status alone.

## Plan Self-Review

- All seven deployed tables have one adapter task and an exact database destination.
- Shared masking occurs before JSON hashing and persistence.
- Every pagination mechanism has a termination and repeated-token guard.
- Read-only boundaries exclude CJ OnStyle, Gmarket/Auction, and AliExpress until authentication and access are actually approved.
- No raw response fixture contains real order or customer data.
- No placeholder implementation steps remain.
