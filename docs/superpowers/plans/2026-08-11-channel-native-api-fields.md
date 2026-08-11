# Channel-Native Order API Fields Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist every documented, non-sensitive order and shipping business field returned by the seven currently implemented channel APIs as typed channel-native SQL columns while retaining masked raw responses and status history.

**Architecture:** Keep one history table per channel and one row per channel order item. Extend existing tables with idempotent SQL migrations, map the new columns in each adapter, and publish a field dictionary that traces every stored column back to its API response path. Preserve channel-native concepts instead of forcing a common dashboard schema.

**Tech Stack:** Python 3.12, pytest, Microsoft SQL Server 2017+, T-SQL, `pymssql`, JSON/XML APIs, Markdown documentation.

## Global Constraints

- Only read-only order, order-detail, and shipping APIs may be called.
- One row represents one channel order item; changes append history and preserve one `IsLatest = 1` row.
- Existing tables and populated columns must not be dropped, renamed, or destructively converted.
- New DDL must be idempotent and use `ALTER TABLE ... ADD` guarded by `COL_LENGTH`.
- API-native status codes and identifiers must be stored without translation or loss of leading zeroes.
- Source timestamps are converted to UTC `datetime2(3)` when timezone semantics are known; date-only values remain `date`.
- API keys, secrets, access tokens, sessions, and plaintext unnecessary PII must never be stored.
- `RawJson` remains masked and supplements rather than replaces typed columns.
- Naver Pay orders are collected through Godomall and distinguished by Godomall channel/order-origin fields; no separate Naver Pay table or collector is created.
- A field is added only when supported by an official contract, a sanitized complete sample, or a verified live response shape.

---

### Task 1: Add a field-coverage contract and migration skeleton

**Files:**
- Create: `tests/fixtures/channel_field_contracts.json`
- Create: `tests/test_channel_field_contracts.py`
- Create: `sql/channel_orders/070_extend_channel_order_api_fields.sql`
- Create: `sql/channel_orders/075_verify_extended_channel_columns.sql`
- Modify: `src/hmr_order_collection/database.py`

**Interfaces:**
- Consumes: existing `TABLES: dict[str, TableDefinition]` and seven deployed `dbo.*_ORDER_ITEM` tables.
- Produces: a machine-readable contract whose entries contain `channel`, `response_path`, `column`, `sql_type`, `nullable`, `classification`, and `evidence`; `classification` is one of `stored`, `masked`, `structural`, or `transport`.

- [ ] **Step 1: Write the failing contract test**

Create a fixture with one initial stored entry for each channel and a test that verifies contract columns are accepted by the corresponding `TableDefinition`:

```python
def test_every_stored_contract_column_is_writable():
    contracts = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    for entry in contracts:
        if entry["classification"] == "stored":
            assert entry["column"] in TABLES[entry["channel"]].columns
```

Add schema validation asserting nonempty response paths, supported classifications, exact SQL types, and an evidence value in `official`, `sample`, or `live`.

- [ ] **Step 2: Run the contract test and verify RED**

Run: `python -m pytest tests/test_channel_field_contracts.py -q`

Expected: FAIL because the fixture names at least one new column absent from `TABLES`.

- [ ] **Step 3: Add guarded migration and writer columns**

Start `070_extend_channel_order_api_fields.sql` with:

```sql
SET NOCOUNT ON;
SET XACT_ABORT ON;

IF COL_LENGTH(N'dbo.NAVER_SMARTSTORE_ORDER_ITEM', N'OrderDate') IS NULL
    ALTER TABLE dbo.NAVER_SMARTSTORE_ORDER_ITEM ADD OrderDate datetime2(3) NULL;
```

Add the corresponding `OrderDate` entry to the Naver `TableDefinition`. Create `075_verify_extended_channel_columns.sql` using a table variable of expected table, column, and SQL type values and throw `51012` when `COL_LENGTH` or `INFORMATION_SCHEMA.COLUMNS` disagrees.

- [ ] **Step 4: Run the focused tests and static SQL checks**

Run:

```powershell
python -m pytest tests/test_channel_field_contracts.py tests/test_database.py -q
git diff --check
```

Expected: PASS and no whitespace errors.

- [ ] **Step 5: Commit**

```powershell
git add tests/fixtures/channel_field_contracts.json tests/test_channel_field_contracts.py sql/channel_orders/070_extend_channel_order_api_fields.sql sql/channel_orders/075_verify_extended_channel_columns.sql src/hmr_order_collection/database.py
git commit -m "test: add channel API field coverage contract"
```

### Task 2: Expand Naver SmartStore order details

**Files:**
- Modify: `tests/fixtures/channel_field_contracts.json`
- Modify: `tests/test_naver.py`
- Modify: `src/hmr_order_collection/channels/naver.py`
- Modify: `src/hmr_order_collection/database.py`
- Modify: `sql/channel_orders/070_extend_channel_order_api_fields.sql`
- Modify: `sql/channel_orders/075_verify_extended_channel_columns.sql`

**Interfaces:**
- Consumes: Naver detail objects with `order`, `productOrder`, and `delivery` sections.
- Produces: typed columns for every documented non-sensitive scalar in those sections; buyer/orderer/receiver/contact/address/customs paths are classified `masked`.

- [ ] **Step 1: Extend the complete Naver fixture and write failing assertions**

Expand the existing synthetic detail response to include at least `orderDate`, `paymentMeans`, `payLocationType`, `orderDiscountAmount`, `generalPaymentAmount`, `deliveryFeeAmount`, `sectionDeliveryFee`, `shippingDueDate`, `placeOrderDate`, `placeOrderStatus`, `expectedDeliveryMethod`, `deliveryAttributeType`, `deliveryMethod`, `wrongProductArrival`, `sendDate`, and `deliveredDate`.

Assert literal mapped values, for example:

```python
assert record.columns["OrderDate"] == "2026-08-11T01:02:03+09:00"
assert record.columns["PaymentMeans"] == "CARD"
assert record.columns["PlaceOrderStatus"] == "OK"
assert record.columns["ShippingDueDate"] == "2026-08-12T23:59:59+09:00"
```

- [ ] **Step 2: Run Naver tests and verify RED**

Run: `python -m pytest tests/test_naver.py tests/test_channel_field_contracts.py -q`

Expected: FAIL with missing new column keys.

- [ ] **Step 3: Implement mappings and SQL columns**

Add the asserted fields to `_map_record`, `TABLES["naver"].columns`, the guarded migration, verification script, and field contract. Keep `productOrderId` as the sole logical identity and retain masking for private fields.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest tests/test_naver.py tests/test_database.py tests/test_channel_field_contracts.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add tests/test_naver.py tests/fixtures/channel_field_contracts.json src/hmr_order_collection/channels/naver.py src/hmr_order_collection/database.py sql/channel_orders/070_extend_channel_order_api_fields.sql sql/channel_orders/075_verify_extended_channel_columns.sql
git commit -m "feat: persist full Naver order detail fields"
```

### Task 3: Expand Godomall including Naver Pay origin fields

**Files:**
- Modify: `tests/fixtures/channel_field_contracts.json`
- Modify: `tests/test_godomall.py`
- Modify: `src/hmr_order_collection/channels/godomall.py`
- Modify: `src/hmr_order_collection/database.py`
- Modify: `sql/channel_orders/070_extend_channel_order_api_fields.sql`
- Modify: `sql/channel_orders/075_verify_extended_channel_columns.sql`

**Interfaces:**
- Consumes: `Order_Search.php` order and `orderGoodsData` item nodes.
- Produces: Godomall-native order, payment, discount, delivery, invoice, and origin fields; `orderChannelFl`, `apiOrderNo`, and available order-type fields distinguish Naver Pay orders in the same table.

- [ ] **Step 1: Write a failing Naver Pay order-origin mapping test**

Add a complete sanitized order containing `orderChannelFl`, `apiOrderNo`, `orderTypeFl`, `settleKind`, `bankSender`, `totalGoodsPrice`, `totalOrderDcPrice`, `totalMemberDcPrice`, `totalCouponGoodsDcPrice`, `totalCouponOrderDcPrice`, `totalMileage`, `totalDeposit`, `orderStatus`, `orderDate`, `paymentDt`, and item-level `goodsCd`, `goodsPrice`, `optionPrice`, `addGoodsPrice`, `goodsDcPrice`, `couponGoodsDcPrice`, `invoiceCompanySno`, `invoiceNo`, and `deliveryDt`.

Assert that a Naver Pay fixture remains one `GODOMALL_ORDER_ITEM` record and preserves its origin:

```python
assert record.columns["OrderChannelCode"] == "naverpay"
assert record.columns["ExternalOrderNo"] == "NPAY-0000123"
assert record.columns["OrderTypeCode"] == "order"
```

- [ ] **Step 2: Run Godomall tests and verify RED**

Run: `python -m pytest tests/test_godomall.py tests/test_channel_field_contracts.py -q`

Expected: FAIL because the expanded typed columns do not exist.

- [ ] **Step 3: Implement complete order/item mappings**

Map order-level totals to repeated order-item history rows, preserve external identifiers as strings, normalize sentinel Godomall dates to `NULL`, and do not introduce a Naver Pay adapter or table.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest tests/test_godomall.py tests/test_database.py tests/test_channel_field_contracts.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add tests/test_godomall.py tests/fixtures/channel_field_contracts.json src/hmr_order_collection/channels/godomall.py src/hmr_order_collection/database.py sql/channel_orders/070_extend_channel_order_api_fields.sql sql/channel_orders/075_verify_extended_channel_columns.sql
git commit -m "feat: persist Godomall and Naver Pay origin fields"
```

### Task 4: Complete Toss Shopping typed field coverage

**Files:**
- Modify: `tests/fixtures/channel_field_contracts.json`
- Modify: `tests/test_toss.py`
- Modify: `src/hmr_order_collection/channels/toss.py`
- Modify: `src/hmr_order_collection/database.py`
- Modify: `sql/channel_orders/070_extend_channel_order_api_fields.sql`
- Modify: `sql/channel_orders/075_verify_extended_channel_columns.sql`

**Interfaces:**
- Consumes: Toss order-product list objects from `/api/v3/shopping-fep/orders/v2`.
- Produces: typed coverage of all non-private order-product fields; address, names, phones, postal code, and shipping note remain masked.

- [ ] **Step 1: Write the failing coverage test**

Use a complete fixture containing every official list-response property. Assert that the current amount, discount, delivery fee, product management, status, timestamps, carrier, and tracking fields remain typed and add any official scalar absent from the current table.

Add an explicit classification assertion:

```python
private_paths = {entry["response_path"] for entry in contracts if entry["channel"] == "toss" and entry["classification"] == "masked"}
assert "receiverPhone" in private_paths
assert "address" in private_paths
```

- [ ] **Step 2: Run Toss tests and verify RED when a documented field is unclassified**

Run: `python -m pytest tests/test_toss.py tests/test_channel_field_contracts.py -q`

Expected: FAIL until every complete-fixture leaf is stored, masked, structural, or transport-classified.

- [ ] **Step 3: Add only genuinely missing typed fields**

Keep official `int64` identifiers and KRW amounts as `bigint`. Do not duplicate private properties as SQL plaintext columns.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest tests/test_toss.py tests/test_database.py tests/test_channel_field_contracts.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add tests/test_toss.py tests/fixtures/channel_field_contracts.json src/hmr_order_collection/channels/toss.py src/hmr_order_collection/database.py sql/channel_orders/070_extend_channel_order_api_fields.sql sql/channel_orders/075_verify_extended_channel_columns.sql
git commit -m "feat: complete Toss Shopping field coverage"
```

### Task 5: Expand Coupang purchase-order fields

**Files:**
- Modify: `tests/fixtures/channel_field_contracts.json`
- Modify: `tests/test_coupang.py`
- Modify: `src/hmr_order_collection/channels/coupang.py`
- Modify: `src/hmr_order_collection/database.py`
- Modify: `sql/channel_orders/070_extend_channel_order_api_fields.sql`
- Modify: `sql/channel_orders/075_verify_extended_channel_columns.sql`

**Interfaces:**
- Consumes: shipment-box objects and nested `orderItems` from the six documented PO status queries.
- Produces: shipment and item fields including release status, split-shipping, remote-price, shipping/departure dates, seller product identifiers, prices, fees, cancellation quantities, carrier, and invoice data.

- [ ] **Step 1: Write failing shipment/item field assertions**

Expand the existing synthetic response with `orderId`, `orderedAt`, `paidAt`, `status`, `splitShipping`, `remotePrice`, `parcelPrintMessage`, `overseaShippingInfoDto`, item `vendorItemId`, `sellerProductId`, `sellerProductItemId`, `shippingCount`, `cancelCount`, `holdCountForCancel`, `estimatedShippingDate`, `plannedShippingDate`, `invoiceNumberUploadDate`, `extraProperties`, and money objects.

Assert that operational non-private fields are typed and `orderer`, `receiver`, tax-receipt private values, and overseas personal identifiers remain masked.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_coupang.py tests/test_channel_field_contracts.py -q`

Expected: FAIL on absent typed columns.

- [ ] **Step 3: Implement shipment/item mappings and guarded DDL**

Correct the existing placeholder `SellerProductItemId = None` to map the documented item property. Preserve nested money conversion through `_money` and external IDs as `nvarchar`.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest tests/test_coupang.py tests/test_database.py tests/test_channel_field_contracts.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add tests/test_coupang.py tests/fixtures/channel_field_contracts.json src/hmr_order_collection/channels/coupang.py src/hmr_order_collection/database.py sql/channel_orders/070_extend_channel_order_api_fields.sql sql/channel_orders/075_verify_extended_channel_columns.sql
git commit -m "feat: persist full Coupang purchase-order fields"
```

### Task 6: Expand LotteON delivery order and progress fields

**Files:**
- Modify: `tests/fixtures/channel_field_contracts.json`
- Modify: `tests/test_lotteon.py`
- Modify: `src/hmr_order_collection/channels/lotteon.py`
- Modify: `src/hmr_order_collection/database.py`
- Modify: `sql/channel_orders/070_extend_channel_order_api_fields.sql`
- Modify: `sql/channel_orders/075_verify_extended_channel_columns.sql`

**Interfaces:**
- Consumes: `SellerDeliveryOrdersSearch` plus `SellerDeliveryProgressStateSearch` rows joined by `odNo + odSeq`.
- Produces: all non-private order, product, quantity, amount, delivery instruction, progress, carrier, invoice, and event-time fields from both APIs.

- [ ] **Step 1: Write a failing two-response join test**

Expand sanitized order and progress fixtures with all scalar business fields observed in the official contract/live response. Assert that order values and latest `dvTrcStatDttm` progress values coexist in one record and that the raw JSON retains separate `deliveryOrder` and `deliveryProgress` objects.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_lotteon.py tests/test_channel_field_contracts.py -q`

Expected: FAIL on missing progress and business columns.

- [ ] **Step 3: Implement mappings, types, and migration**

Continue selecting the latest progress event per identity. Classify every field in `_PRIVATE_FIELDS` as masked and never add it as a plaintext SQL column.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest tests/test_lotteon.py tests/test_database.py tests/test_channel_field_contracts.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add tests/test_lotteon.py tests/fixtures/channel_field_contracts.json src/hmr_order_collection/channels/lotteon.py src/hmr_order_collection/database.py sql/channel_orders/070_extend_channel_order_api_fields.sql sql/channel_orders/075_verify_extended_channel_columns.sql
git commit -m "feat: persist full LotteON delivery fields"
```

### Task 7: Join all verified SSG shipping-stage APIs

**Files:**
- Modify: `tests/fixtures/channel_field_contracts.json`
- Modify: `tests/test_ssg.py`
- Modify: `src/hmr_order_collection/channels/ssg.py`
- Modify: `src/hmr_order_collection/database.py`
- Modify: `sql/channel_orders/070_extend_channel_order_api_fields.sql`
- Modify: `sql/channel_orders/075_verify_extended_channel_columns.sql`

**Interfaces:**
- Consumes: `listShppDirection.ssg`, `listWarehouseOut.ssg`, `listNonDelivery.ssg`, and `listDeliveryEnd.ssg` responses.
- Produces: one SSG history record per `OrdNo + OrdItemSeq + ShppNo + ShppSeq`, containing all non-private order-direction, warehouse-out, in-delivery, and delivery-end fields returned successfully.

- [ ] **Step 1: Write failing endpoint-join tests**

Add sanitized fixtures for all four endpoint shapes. Assert that matching identities merge status codes, scheduled date, actual warehouse-out/dispatch time, carrier, invoice, delivery progress, and delivery-end time into one record. Add a test that `listNonDelivery.ssg` business failure `resultCode=99` raises a named partial-collection error rather than silently producing no rows.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_ssg.py tests/test_channel_field_contracts.py -q`

Expected: FAIL because the adapter currently calls only `listShppDirection.ssg`.

- [ ] **Step 3: Implement read-only calls and identity join**

Call the four endpoints with their documented request envelopes. Merge only successful responses; surface the known non-delivery permission/business error as a partial run so the database transaction does not claim complete coverage.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest tests/test_ssg.py tests/test_database.py tests/test_channel_field_contracts.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add tests/test_ssg.py tests/fixtures/channel_field_contracts.json src/hmr_order_collection/channels/ssg.py src/hmr_order_collection/database.py sql/channel_orders/070_extend_channel_order_api_fields.sql sql/channel_orders/075_verify_extended_channel_columns.sql
git commit -m "feat: collect full SSG shipping lifecycle fields"
```

### Task 8: Expand the verified 11st feeds without inventing unsupported fields

**Files:**
- Modify: `tests/fixtures/channel_field_contracts.json`
- Modify: `tests/test_elevenst.py`
- Modify: `src/hmr_order_collection/channels/elevenst.py`
- Modify: `src/hmr_order_collection/database.py`
- Modify: `sql/channel_orders/070_extend_channel_order_api_fields.sql`
- Modify: `sql/channel_orders/075_verify_extended_channel_columns.sql`

**Interfaces:**
- Consumes: the verified `complete` and `shipping` XML feeds.
- Produces: typed coverage for every non-private scalar returned by those two feeds, using the higher-precedence shipping record for overlapping identities.

- [ ] **Step 1: Write failing namespace-complete XML tests**

Use full sanitized XML nodes from both verified feeds, including order/product identifiers, quantities, monetary fields, status codes, order/payment/dispatch dates, carrier, invoice, seller management codes, and shipping-fee fields. Assert exact values after namespace removal and state precedence.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_elevenst.py tests/test_channel_field_contracts.py -q`

Expected: FAIL for untyped verified fields.

- [ ] **Step 3: Implement only verified mappings**

Do not add columns from the unverified endpoints that previously returned `500/-997`. Classify private XML paths as masked and response wrappers as structural/transport.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest tests/test_elevenst.py tests/test_database.py tests/test_channel_field_contracts.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add tests/test_elevenst.py tests/fixtures/channel_field_contracts.json src/hmr_order_collection/channels/elevenst.py src/hmr_order_collection/database.py sql/channel_orders/070_extend_channel_order_api_fields.sql sql/channel_orders/075_verify_extended_channel_columns.sql
git commit -m "feat: persist complete verified 11st feed fields"
```

### Task 9: Generate the field dictionary and verify deployment safely

**Files:**
- Create: `src/hmr_order_collection/field_dictionary.py`
- Create: `tests/test_field_dictionary.py`
- Create: `docs/channel-api-field-dictionary.md`
- Modify: `docs/channel-order-tables.md`
- Modify: `SALES_TEAM_ORDER_COLLECTION_STATUS.md`

**Interfaces:**
- Consumes: `tests/fixtures/channel_field_contracts.json` and deployed SQL metadata.
- Produces: deterministic Markdown grouped by channel with API, response path, DB table/column, SQL type, nullability, description/meaning, transformation, and evidence.

- [ ] **Step 1: Write the failing deterministic-render test**

```python
def test_render_field_dictionary_is_grouped_and_stable():
    rendered = render_field_dictionary(CONTRACT_PATH)
    assert rendered.startswith("# 채널별 주문·배송 API 필드 사전\n")
    assert "## 네이버 스마트스토어" in rendered
    assert "## 한촌몰·고도몰(네이버페이 포함)" in rendered
    assert rendered.index("## 네이버 스마트스토어") < rendered.index("## 토스쇼핑")
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_field_dictionary.py -q`

Expected: FAIL because `field_dictionary.py` does not exist.

- [ ] **Step 3: Implement the renderer and generate documentation**

Implement `render_field_dictionary(path: Path) -> str` with fixed channel and column ordering. Generate `docs/channel-api-field-dictionary.md`; document migration execution order `070` then `075`, and state explicitly that Naver Pay is contained in `GODOMALL_ORDER_ITEM`.

- [ ] **Step 4: Run full local verification**

Run:

```powershell
python -m pytest -q
git diff --check
rg -n "access_token|client_secret|secret_key|partner_key|user_key" docs/channel-api-field-dictionary.md sql/channel_orders/070_extend_channel_order_api_fields.sql
```

Expected: all tests pass; no secret values or authentication columns appear.

- [ ] **Step 5: Run SQL verification against the approved ecommerce database**

Execute `070_extend_channel_order_api_fields.sql` and then `075_verify_extended_channel_columns.sql` using credentials loaded from `.env` without printing them. Run `070` a second time and re-run `075`.

Expected: both migration executions succeed, verification succeeds after each execution, and existing row counts are unchanged.

- [ ] **Step 6: Commit**

```powershell
git add src/hmr_order_collection/field_dictionary.py tests/test_field_dictionary.py docs/channel-api-field-dictionary.md docs/channel-order-tables.md SALES_TEAM_ORDER_COLLECTION_STATUS.md sql/channel_orders tests/fixtures/channel_field_contracts.json
git commit -m "docs: publish channel API field dictionary"
```

## Plan Self-Review

- Spec coverage: explicit tasks cover all seven implemented channels, Godomall-hosted Naver Pay, typed native columns, masked raw JSON, API joining, migration safety, history preservation, field traceability, and verification.
- Scope: common dashboard views, normalized statuses, alert rules, settlement/advertising/inventory domains, and unauthorized channels remain excluded.
- Type consistency: external marketplace identifiers remain strings except Toss fields guaranteed as `int64`; times use `datetime2(3)` and date-only values use `date`.
- TDD: every production change begins with a focused failing behavior test and includes the expected RED and GREEN commands.
- Placeholder scan: the plan contains no deferred implementation markers; newly discovered response fields must enter the explicit stored/masked/structural/transport contract before code is accepted.
