# Channel Order Tables Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create seven SQL Server `dbo` tables that store one row per channel order item while preserving status history, masked JSON, and efficient latest-row lookup.

**Architecture:** Each verified sales channel owns one `dbo.*_ORDER_ITEM` table with channel-native business columns and a common set of collection metadata. Inserts are append-only; a filtered unique index guarantees at most one `IsLatest = 1` row per channel order-item identity. Separate SQL scripts create tables, create indexes, verify behavior, and remove only the objects introduced by this feature.

**Tech Stack:** Microsoft SQL Server 2017+ (SSMS), T-SQL, `datetime2(3)`, `nvarchar(max)` JSON with `ISJSON`, SHA-256 payload hashes in `binary(32)`.

## Global Constraints

- Target database is `ecommerce`; scripts must refuse to run in `master`, `model`, `msdb`, or `tempdb`.
- Use the existing `dbo` schema; do not create or reference an `stg` schema.
- Table names use uppercase English snake case.
- One row represents one order item; status changes append a new row instead of overwriting history.
- Only masked JSON may be written to `RawJson`; API keys, secrets, and tokens must never be stored.
- All database-generated timestamps use `SYSUTCDATETIME()` and `datetime2(3)`.
- External identifiers use `nvarchar` unless the channel contract explicitly guarantees `int64`.
- DDL scripts are idempotent and use `SET XACT_ABORT ON`.
- No script may execute order confirmation, shipping, cancellation, or other external state-changing APIs.

---

### Task 1: Add SQL Server prerequisites and object-contract verification

**Files:**
- Create: `sql/channel_orders/001_database_prerequisites.sql`
- Create: `sql/channel_orders/005_verify_object_contract.sql`

**Interfaces:**
- Consumes: SQL Server connection whose current database is `ecommerce`.
- Produces: A safe execution preamble and a reusable object-contract check for all later tasks.

- [ ] **Step 1: Write the failing object-contract verification**

Create `005_verify_object_contract.sql` with an expected-object table and failure aggregation:

```sql
SET NOCOUNT ON;
SET XACT_ABORT ON;

DECLARE @ExpectedTables table (TableName sysname NOT NULL PRIMARY KEY);
INSERT @ExpectedTables (TableName) VALUES
('NAVER_SMARTSTORE_ORDER_ITEM'),
('GODOMALL_ORDER_ITEM'),
('COUPANG_ORDER_ITEM'),
('LOTTEON_ORDER_ITEM'),
('ELEVENST_ORDER_ITEM'),
('SSG_ORDER_ITEM'),
('TOSS_SHOPPING_ORDER_ITEM');

DECLARE @Missing nvarchar(max);
SELECT @Missing = STRING_AGG(e.TableName, ', ')
FROM @ExpectedTables e
WHERE OBJECT_ID(N'dbo.' + e.TableName, N'U') IS NULL;

IF @Missing IS NOT NULL
BEGIN
    DECLARE @MissingMessage nvarchar(2048) = N'Missing channel order tables: ' + @Missing;
    THROW 51001, @MissingMessage, 1;
END;
```

Append this common-column check so every table must have `StagingId`, `CollectionRunId`, `CollectedAt`, `RawJson`, `PayloadHash`, `IsLatest`, and `CreatedAt`:

```sql
DECLARE @CommonColumns table (ColumnName sysname NOT NULL PRIMARY KEY);
INSERT @CommonColumns (ColumnName) VALUES
('StagingId'), ('CollectionRunId'), ('CollectedAt'), ('RawJson'),
('PayloadHash'), ('IsLatest'), ('CreatedAt');

DECLARE @MissingColumns nvarchar(max);
SELECT @MissingColumns = STRING_AGG(e.TableName + N'.' + c.ColumnName, N', ')
FROM @ExpectedTables e
CROSS JOIN @CommonColumns c
WHERE OBJECT_ID(N'dbo.' + e.TableName, N'U') IS NOT NULL
  AND COL_LENGTH(N'dbo.' + e.TableName, c.ColumnName) IS NULL;

IF @MissingColumns IS NOT NULL
BEGIN
    DECLARE @MissingColumnMessage nvarchar(2048) =
        N'Missing common channel columns: ' + @MissingColumns;
    THROW 51002, @MissingColumnMessage, 1;
END;
```

- [ ] **Step 2: Run verification and confirm it fails before DDL exists**

Run in SSMS SQLCMD mode or with `sqlcmd`:

```powershell
sqlcmd -S 222.122.41.213 -d ecommerce -E -b -i sql/channel_orders/005_verify_object_contract.sql
```

Expected: non-zero exit with `51001` and all seven missing table names. If SQL authentication is required, use an interactive SSMS connection; do not put its password in a script or shell history.

- [ ] **Step 3: Add the database safety preamble**

Create `001_database_prerequisites.sql`:

```sql
SET NOCOUNT ON;
SET XACT_ABORT ON;

IF DB_NAME() IN (N'master', N'model', N'msdb', N'tempdb')
    THROW 51000, N'Refusing to create channel order tables in a system database.', 1;

IF SCHEMA_ID(N'dbo') IS NULL
    THROW 51000, N'Required dbo schema does not exist.', 1;

SELECT DB_NAME() AS TargetDatabase,
       CAST(SERVERPROPERTY('ProductVersion') AS nvarchar(128)) AS SqlServerVersion;
```

- [ ] **Step 4: Run the preamble in `ecommerce`**

Expected: one row showing `TargetDatabase = ecommerce`; no objects are created.

- [ ] **Step 5: Commit**

```powershell
git add sql/channel_orders/001_database_prerequisites.sql sql/channel_orders/005_verify_object_contract.sql
git commit -m "test: add channel table contract checks"
```

### Task 2: Create Naver SmartStore and Godomall order-item tables

**Files:**
- Create: `sql/channel_orders/010_create_naver_godomall_tables.sql`
- Modify: `sql/channel_orders/005_verify_object_contract.sql`

**Interfaces:**
- Consumes: Common metadata contract from Task 1.
- Produces: `dbo.NAVER_SMARTSTORE_ORDER_ITEM` and `dbo.GODOMALL_ORDER_ITEM`.

- [ ] **Step 1: Extend the verification with required channel columns**

Add assertions for these exact columns:

```text
NAVER_SMARTSTORE_ORDER_ITEM: ProductOrderId, OrderId, ProductId, OptionId,
ProductName, OptionName, Quantity, UnitPrice, TotalPaymentAmount,
ProductOrderStatus, ClaimStatus, DeliveryStatus, PaymentAt, DispatchAt,
DeliveryCompletedAt, DeliveryCompanyCode, TrackingNumber

GODOMALL_ORDER_ITEM: OrderNo, OrderItemSno, OrderChannelCode,
ExternalOrderNo, ProductCode, OptionCode, ProductName, OptionName, Quantity,
UnitPrice, PaymentAmount, DiscountAmount, DeliveryFee, OrderStatus,
PaymentStatus, DeliveryStatus, OrderedAt, PaidAt, DispatchedAt,
DeliveryCompanyCode, TrackingNumber
```

Expected before implementation: verification still fails with the two missing tables.

- [ ] **Step 2: Create the two tables idempotently**

Implement `010_create_naver_godomall_tables.sql`. Both tables must start with this common contract:

```sql
StagingId bigint IDENTITY(1,1) NOT NULL,
CollectionRunId uniqueidentifier NOT NULL,
CollectedAt datetime2(3) NOT NULL,
SourceCreatedAt datetime2(3) NULL,
SourceModifiedAt datetime2(3) NULL,
RawOrderStatus nvarchar(100) NULL,
RawDeliveryStatus nvarchar(100) NULL,
RawJson nvarchar(max) NOT NULL,
PayloadHash binary(32) NOT NULL,
IsLatest bit NOT NULL CONSTRAINT DF_<TABLE>_IsLatest DEFAULT (1),
CreatedAt datetime2(3) NOT NULL CONSTRAINT DF_<TABLE>_CreatedAt DEFAULT (SYSUTCDATETIME()),
CONSTRAINT PK_<TABLE> PRIMARY KEY CLUSTERED (StagingId),
CONSTRAINT CK_<TABLE>_RawJson CHECK (ISJSON(RawJson) = 1)
```

Use `nvarchar(100)` for IDs and status codes, `nvarchar(500)` for names/options, `int` for quantities, `decimal(19,4)` for monetary values, and `datetime2(3)` for source timestamps. Mark the logical identifiers listed in the design document `NOT NULL`; channel fields not guaranteed by the API remain nullable.

- [ ] **Step 3: Execute the DDL twice**

Run `001_database_prerequisites.sql`, then `010_create_naver_godomall_tables.sql` twice.

Expected: both executions succeed and exactly two new tables exist; the second execution makes no changes.

- [ ] **Step 4: Run the contract verification**

Expected: verification reports only the five tables not implemented yet, not either table from this task.

- [ ] **Step 5: Commit**

```powershell
git add sql/channel_orders/005_verify_object_contract.sql sql/channel_orders/010_create_naver_godomall_tables.sql
git commit -m "feat: add Naver and Godomall order tables"
```

### Task 3: Create Coupang and LotteON order-item tables

**Files:**
- Create: `sql/channel_orders/020_create_coupang_lotteon_tables.sql`
- Modify: `sql/channel_orders/005_verify_object_contract.sql`

**Interfaces:**
- Consumes: Common metadata and type rules from Tasks 1-2.
- Produces: `dbo.COUPANG_ORDER_ITEM` and `dbo.LOTTEON_ORDER_ITEM`.

- [ ] **Step 1: Add failing required-column assertions**

```text
COUPANG_ORDER_ITEM: ShipmentBoxId, OrderId, OrderItemId, VendorItemId,
SellerProductId, SellerProductItemId, ProductName, OptionName, Quantity,
CanceledQuantity, SalesPrice, OrderStatus, DeliveryStatus, OrderedAt, PaidAt,
EstimatedShippingAt, DispatchedAt, DeliveryCompletedAt,
DeliveryCompanyCode, TrackingNumber

LOTTEON_ORDER_ITEM: OrderNo, OrderItemSeq, ProductId, OptionId, ProductName,
OptionName, Quantity, CanceledQuantity, SalesAmount, PaymentAmount,
OrderStatus, DeliveryStatus, OrderedAt, PaidAt, DispatchedAt,
DeliveryCompletedAt, DeliveryCompanyCode, TrackingNumber
```

- [ ] **Step 2: Create the two tables**

Implement `020_create_coupang_lotteon_tables.sql` with the common contract from Task 2. Use `nvarchar(100)` for marketplace identifiers, including numeric-looking Coupang IDs, so format changes and leading zeros remain lossless. Use `decimal(19,4)` for prices and amounts.

- [ ] **Step 3: Execute twice and verify idempotency**

Expected: no errors; exactly four total channel tables now exist.

- [ ] **Step 4: Run the contract verification**

Expected: only `ELEVENST_ORDER_ITEM`, `SSG_ORDER_ITEM`, and `TOSS_SHOPPING_ORDER_ITEM` remain missing.

- [ ] **Step 5: Commit**

```powershell
git add sql/channel_orders/005_verify_object_contract.sql sql/channel_orders/020_create_coupang_lotteon_tables.sql
git commit -m "feat: add Coupang and LotteON order tables"
```

### Task 4: Create 11st and SSG order-item tables

**Files:**
- Create: `sql/channel_orders/030_create_elevenst_ssg_tables.sql`
- Modify: `sql/channel_orders/005_verify_object_contract.sql`

**Interfaces:**
- Produces: `dbo.ELEVENST_ORDER_ITEM` and `dbo.SSG_ORDER_ITEM`.

- [ ] **Step 1: Add failing required-column assertions**

```text
ELEVENST_ORDER_ITEM: OrderNo, OrderProductNo, ProductId, OptionId,
ProductName, OptionName, Quantity, OrderAmount, OrderStatus, DeliveryStatus,
OrderedAt, PaidAt, DispatchedAt, DeliveryCompanyCode, TrackingNumber

SSG_ORDER_ITEM: OrdNo, OrdItemSeq, ShppNo, ShppSeq, SiteNo, ItemId, UitemId,
SplVenItemId, USplVenItemId, ItemName, UnitItemName, OrderQuantity,
DirectedQuantity, CanceledQuantity, SupplyPrice, SalesPrice, RealOrderAmount,
DiscountAmount, OrderStatusCode, ShippingStatusCode,
ShippingProgressDetailCode, OrderReceivedAt, OrderCompletedAt,
ScheduledShippingDate
```

- [ ] **Step 2: Create the tables**

Implement `030_create_elevenst_ssg_tables.sql`. Store `OrdItemSeq`, `ShppSeq`, and 11st order-product numbers as `nvarchar(100)` because their external representation is controlled by the channel. Store `ScheduledShippingDate` as `date`; other source times use `datetime2(3)`.

- [ ] **Step 3: Execute twice and verify**

Expected: six total channel tables exist and only the Toss table is missing from the contract check.

- [ ] **Step 4: Commit**

```powershell
git add sql/channel_orders/005_verify_object_contract.sql sql/channel_orders/030_create_elevenst_ssg_tables.sql
git commit -m "feat: add 11st and SSG order tables"
```

### Task 5: Create the Toss Shopping order-item table

**Files:**
- Create: `sql/channel_orders/040_create_toss_shopping_table.sql`
- Modify: `sql/channel_orders/005_verify_object_contract.sql`

**Interfaces:**
- Produces: `dbo.TOSS_SHOPPING_ORDER_ITEM` keyed logically by `OrderProductId`.

- [ ] **Step 1: Add the failing Toss column contract**

Require these columns:

```text
OrderId, OrderProductId, ProductId, StockId, ProductName, OptionName,
Quantity, Price, OriginPrice, TotalDiscountPrice, TossShoppingDiscount,
TossPayDiscount, TossPayPoint, OrderProductStatus, OrderedAt, CanceledAt,
ConfirmedAt, ShippingDeadlineAt, DeliveryCompanyCode,
ShippingTrackingNumber, DeliveryFeeGroupId, DeliveryFee,
DeliveryLocationType, NormalDeliveryFee, JejuDeliveryFee,
MountainDeliveryFee, ProductManagementCode, ProductItemManagementCode
```

- [ ] **Step 2: Create the Toss table**

Implement `040_create_toss_shopping_table.sql` with `bigint` for `OrderId`, `OrderProductId`, `ProductId`, `StockId`, and `DeliveryFeeGroupId`, matching the official `int64` contract. Use `bigint` for the KRW integer amount fields and `datetime2(3)` for timestamp fields.

Do not create columns for orderer, receiver, phone, or address plaintext. Those fields exist in the API but are not needed for the current dashboard and must be present only as masked tokens in `RawJson`.

- [ ] **Step 3: Execute twice and run the full contract verification**

Expected: both DDL runs succeed; `005_verify_object_contract.sql` exits successfully with no missing table or column messages.

- [ ] **Step 4: Insert a masked Toss sample row**

Use a transaction and roll it back:

```sql
BEGIN TRANSACTION;
INSERT dbo.TOSS_SHOPPING_ORDER_ITEM
(
  CollectionRunId, CollectedAt, OrderId, OrderProductId, ProductId, StockId,
  ProductName, OptionName, Quantity, Price, OrderProductStatus,
  RawOrderStatus, RawDeliveryStatus, RawJson, PayloadHash, IsLatest
)
VALUES
(
  NEWID(), SYSUTCDATETIME(), 10001, 20001, 30001, 40001,
  N'마스킹 테스트 상품', N'옵션: 테스트', 1, 10000, N'DELIVERED',
  N'DELIVERED', N'DELIVERED',
  N'{"orderProductId":20001,"ordererName":"***","receiverPhone":"***"}',
  HASHBYTES('SHA2_256', N'{"orderProductId":20001,"ordererName":"***","receiverPhone":"***"}'),
  1
);
ROLLBACK TRANSACTION;
```

Expected: insert succeeds and rollback leaves the table empty.

- [ ] **Step 5: Commit**

```powershell
git add sql/channel_orders/005_verify_object_contract.sql sql/channel_orders/040_create_toss_shopping_table.sql
git commit -m "feat: add Toss Shopping order table"
```

### Task 6: Add latest-row, collection-run, and payload indexes

**Files:**
- Create: `sql/channel_orders/050_create_channel_order_indexes.sql`
- Create: `sql/channel_orders/060_verify_history_constraints.sql`

**Interfaces:**
- Consumes: all seven tables.
- Produces: deterministic latest-row queries and uniqueness enforcement.

- [ ] **Step 1: Write the failing history verification**

Create `060_verify_history_constraints.sql` to assert each table has:

- `IX_<TABLE>_CollectionRunId`
- `IX_<TABLE>_Identity_CollectedAt`
- `UX_<TABLE>_Latest` filtered with `WHERE IsLatest = 1`
- `IX_<TABLE>_Identity_PayloadHash`

Query `sys.indexes` and `sys.index_columns`; throw `51003` with missing index names. Expected before Task 6 implementation: failure listing 28 indexes.

- [ ] **Step 2: Create indexes idempotently**

Implement `050_create_channel_order_indexes.sql` using `IF NOT EXISTS` checks. For example:

```sql
CREATE UNIQUE NONCLUSTERED INDEX UX_TOSS_SHOPPING_ORDER_ITEM_Latest
ON dbo.TOSS_SHOPPING_ORDER_ITEM (OrderProductId)
WHERE IsLatest = 1;

CREATE NONCLUSTERED INDEX IX_TOSS_SHOPPING_ORDER_ITEM_Identity_CollectedAt
ON dbo.TOSS_SHOPPING_ORDER_ITEM (OrderProductId, CollectedAt DESC)
INCLUDE (OrderId, OrderProductStatus, DeliveryCompanyCode, ShippingTrackingNumber);

CREATE NONCLUSTERED INDEX IX_TOSS_SHOPPING_ORDER_ITEM_Identity_PayloadHash
ON dbo.TOSS_SHOPPING_ORDER_ITEM (OrderProductId, PayloadHash);

CREATE NONCLUSTERED INDEX IX_TOSS_SHOPPING_ORDER_ITEM_CollectionRunId
ON dbo.TOSS_SHOPPING_ORDER_ITEM (CollectionRunId);
```

Repeat with each channel's logical identity from the design spec.

- [ ] **Step 3: Verify the latest-row invariant**

In a rolled-back transaction, insert one Toss row with `IsLatest = 1`, then attempt a second row with the same `OrderProductId` and `IsLatest = 1`.

Expected: SQL Server error `2601` or `2627`. Update the first row to `IsLatest = 0`, insert the second row, and verify exactly one latest row and two total history rows before rollback.

- [ ] **Step 4: Run both verification scripts**

Expected: `005_verify_object_contract.sql` and `060_verify_history_constraints.sql` both succeed.

- [ ] **Step 5: Commit**

```powershell
git add sql/channel_orders/050_create_channel_order_indexes.sql sql/channel_orders/060_verify_history_constraints.sql
git commit -m "feat: enforce channel order history indexes"
```

### Task 7: Add end-to-end verification, rollback, and operator documentation

**Files:**
- Create: `sql/channel_orders/090_verify_channel_order_tables.sql`
- Create: `sql/channel_orders/099_drop_channel_order_tables.sql`
- Create: `docs/channel-order-tables.md`
- Modify: `SALES_TEAM_ORDER_COLLECTION_STATUS.md`

**Interfaces:**
- Consumes: every DDL and verification script.
- Produces: repeatable deployment and recovery instructions for SSMS operators.

- [ ] **Step 1: Create the end-to-end verification script**

`090_verify_channel_order_tables.sql` must:

1. Execute the object and index checks using SQLCMD `:r` includes.
2. Verify every `RawJson` check constraint is enabled and trusted.
3. Insert one masked sample into each table inside a transaction.
4. Verify seven inserted rows and seven distinct `CollectionRunId` values.
5. Roll back and verify no sample rows remain.

Use only fictitious IDs and `***` for personal fields.

- [ ] **Step 2: Create the rollback script**

`099_drop_channel_order_tables.sql` must require an explicit SQLCMD variable:

```sql
:setvar CONFIRM_DROP "NO"
IF N'$(CONFIRM_DROP)' <> N'YES'
    THROW 51009, N'Set CONFIRM_DROP=YES to remove channel order tables.', 1;
```

Drop only the seven tables, in reverse creation order, with `IF OBJECT_ID(..., 'U') IS NOT NULL`. Do not drop `dbo` or unrelated ecommerce objects.

- [ ] **Step 3: Write the operator guide**

Document:

- Exact execution order: `001`, `010`, `020`, `030`, `040`, `050`, `090`.
- Target database confirmation in SSMS.
- How to run scripts twice to validate idempotency.
- How `IsLatest` history insertion must run inside a transaction.
- UTC timestamp and masking rules.
- How to run rollback with `CONFIRM_DROP=YES` in a non-production test database first.

- [ ] **Step 4: Update the status document**

Add a SQL implementation section listing the seven `dbo.*_ORDER_ITEM` tables, the deployment verification result, and the latest-row rule. Do not state that production deployment occurred unless it was actually executed against `ecommerce` and verified.

- [ ] **Step 5: Run static and database verification**

```powershell
git diff --check
rg -n "stg\.|CREATE SCHEMA|API_KEY|SECRET_KEY|ACCESS_TOKEN" sql docs
```

Expected: no `stg.` or `CREATE SCHEMA`; key names may appear only in prose that states they must not be stored, never as values. Execute `090_verify_channel_order_tables.sql` in a disposable or approved test database and expect success.

- [ ] **Step 6: Commit**

```powershell
git add sql/channel_orders docs/channel-order-tables.md SALES_TEAM_ORDER_COLLECTION_STATUS.md
git commit -m "docs: add channel order table deployment guide"
```

## Plan Self-Review

- Spec coverage: all seven approved channel tables, one-row-per-order-item, history retention, masked JSON, indexes, verification, and rollback are assigned to tasks.
- Placeholder scan: no `TBD`, `TODO`, or deferred implementation steps remain.
- Type consistency: external IDs are `nvarchar` except official Toss `int64` fields; all common metadata names match the design spec.
- Scope: common normalized tables and dashboard VIEW remain explicitly outside this plan.
