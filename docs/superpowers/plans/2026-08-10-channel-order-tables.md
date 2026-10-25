# 채널 주문 테이블 구현 계획

> **에이전트 작업자 안내:** 필수 하위 스킬로 superpowers:subagent-driven-development(권장) 또는 superpowers:executing-plans를 사용하여 이 계획을 작업별로 구현합니다. 진행 상황은 체크박스(`- [ ]`)로 추적합니다.

**목표:** 주문상품당 한 행을 저장하고 상태 이력, 마스킹 JSON 및 효율적인 최신 행 조회를 지원하는 SQL Server `dbo` 테이블 7개를 생성합니다.

**구조:** 검증된 판매 채널마다 채널 고유 업무 컬럼과 공통 수집 메타데이터를 갖춘 `dbo.*_ORDER_ITEM` 테이블을 하나씩 둡니다. 데이터는 이력 행 추가 방식으로 저장하며, 필터형 고유 인덱스로 주문상품 식별자당 `IsLatest = 1` 행을 최대 하나로 보장합니다. 테이블 생성, 인덱스 생성, 동작 검증 및 이 기능에서 추가한 객체만 제거하는 SQL을 각각 분리합니다.

**기술 스택:** Microsoft SQL Server 2017+ 및 SSMS, T-SQL, `datetime2(3)`, `ISJSON`으로 검증하는 `nvarchar(max)` JSON, `binary(32)`의 SHA-256 페이로드 해시.

## 공통 제약 사항

- 대상 DB는 `ecommerce`이며 `master`, `model`, `msdb`, `tempdb`에서는 실행을 거부합니다.
- 기존 `dbo` 스키마를 사용하고 `stg` 스키마를 생성하거나 참조하지 않습니다.
- 테이블명은 대문자 영문 스네이크 표기법을 사용합니다.
- 한 행은 주문상품 하나를 나타냅니다. 상태 변경 시 이력을 덮어쓰지 않고 새 행을 추가합니다.
- `RawJson`에는 마스킹된 JSON만 저장하고 API 키, 비밀키, 토큰은 저장하지 않습니다.
- DB가 생성하는 시각은 `SYSUTCDATETIME()`과 `datetime2(3)`을 사용합니다.
- 채널 계약에서 `int64`를 명시적으로 보장하지 않는 외부 식별자는 `nvarchar`를 사용합니다.
- DDL은 멱등성을 보장하고 `SET XACT_ABORT ON`을 사용합니다.
- 주문 확인·배송·취소 등 외부 상태 변경 API를 실행하지 않습니다.

---

### 작업 1: SQL Server 사전 조건 및 객체 계약 검증 추가

**파일:**
- 생성: `sql/channel_orders/001_database_prerequisites.sql`
- 생성: `sql/channel_orders/005_verify_object_contract.sql`

**인터페이스:**
- 입력: 현재 DB가 `ecommerce`인 SQL Server 연결.
- 산출물: 안전한 실행 사전 점검과 후속 작업에서 재사용할 객체 계약 검증.

- [ ] **단계 1: 실패하는 객체 계약 검증 작성**

예상 객체 목록과 실패 집계 기능을 갖춘 `005_verify_object_contract.sql`을 생성합니다:

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

모든 테이블에 `StagingId`, `CollectionRunId`, `CollectedAt`, `RawJson`, `PayloadHash`, `IsLatest`, `CreatedAt`이 있는지 검사하는 다음 공통 컬럼 검증을 추가합니다:

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

- [ ] **단계 2: DDL 생성 전에 검증이 실패하는지 확인**

SSMS SQLCMD 모드 또는 `sqlcmd`로 실행합니다:

```powershell
sqlcmd -S 222.122.41.213 -d ecommerce -E -b -i sql/channel_orders/005_verify_object_contract.sql
```

예상 결과: 오류 `51001`과 누락된 7개 테이블명이 표시되고 0이 아닌 코드로 종료됩니다. SQL 인증이 필요하면 SSMS에서 대화형으로 연결하고 비밀번호를 스크립트나 셸 이력에 남기지 않습니다.

- [ ] **단계 3: DB 안전 사전 점검 추가**

`001_database_prerequisites.sql`을 생성합니다:

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

- [ ] **단계 4: `ecommerce`에서 사전 점검 실행**

예상 결과: `TargetDatabase = ecommerce`인 한 행이 표시되며 객체는 생성되지 않습니다.

- [ ] **단계 5: 커밋**

```powershell
git add sql/channel_orders/001_database_prerequisites.sql sql/channel_orders/005_verify_object_contract.sql
git commit -m "test: add channel table contract checks"
```

### 작업 2: 네이버 스마트스토어·고도몰 주문상품 테이블 생성

**파일:**
- 생성: `sql/channel_orders/010_create_naver_godomall_tables.sql`
- 수정: `sql/channel_orders/005_verify_object_contract.sql`

**인터페이스:**
- 입력: 작업 1의 공통 메타데이터 계약.
- 산출물: `dbo.NAVER_SMARTSTORE_ORDER_ITEM`, `dbo.GODOMALL_ORDER_ITEM`.

- [ ] **단계 1: 필수 채널 컬럼 검증 확장**

다음 컬럼을 정확히 검증하도록 단언을 추가합니다:

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

구현 전 예상 결과: 두 테이블이 누락되어 검증이 계속 실패합니다.

- [ ] **단계 2: 멱등성을 갖춘 두 테이블 생성**

`010_create_naver_godomall_tables.sql`을 구현합니다. 두 테이블 모두 다음 공통 계약으로 시작해야 합니다:

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

ID·상태 코드는 `nvarchar(100)`, 이름·옵션은 `nvarchar(500)`, 수량은 `int`, 금액은 `decimal(19,4)`, 원본 시각은 `datetime2(3)`을 사용합니다. 설계 문서의 논리 식별자는 `NOT NULL`로 지정하고 API가 보장하지 않는 채널 필드는 NULL을 허용합니다.

- [ ] **단계 3: DDL 두 번 실행**

`001_database_prerequisites.sql` 실행 후 `010_create_naver_godomall_tables.sql`을 두 번 실행합니다.

예상 결과: 두 번 모두 성공하고 새 테이블은 정확히 2개이며 두 번째 실행에서는 변경이 없습니다.

- [ ] **단계 4: 계약 검증 실행**

예상 결과: 이 작업의 두 테이블은 누락으로 보고되지 않고 아직 구현하지 않은 5개 테이블만 표시됩니다.

- [ ] **단계 5: 커밋**

```powershell
git add sql/channel_orders/005_verify_object_contract.sql sql/channel_orders/010_create_naver_godomall_tables.sql
git commit -m "feat: add Naver and Godomall order tables"
```

### 작업 3: 쿠팡·롯데ON 주문상품 테이블 생성

**파일:**
- 생성: `sql/channel_orders/020_create_coupang_lotteon_tables.sql`
- 수정: `sql/channel_orders/005_verify_object_contract.sql`

**인터페이스:**
- 입력: 작업 1~2의 공통 메타데이터와 자료형 규칙.
- 산출물: `dbo.COUPANG_ORDER_ITEM`, `dbo.LOTTEON_ORDER_ITEM`.

- [ ] **단계 1: 실패하는 필수 컬럼 단언 추가**

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

- [ ] **단계 2: 두 테이블 생성**

작업 2의 공통 계약에 따라 `020_create_coupang_lotteon_tables.sql`을 구현합니다. 숫자처럼 보이는 쿠팡 ID를 포함한 쇼핑몰 식별자는 `nvarchar(100)`을 사용하여 형식 변경이나 앞자리 0을 보존합니다. 가격과 금액은 `decimal(19,4)`를 사용합니다.

- [ ] **단계 3: 두 번 실행하여 멱등성 검증**

예상 결과: 오류 없이 채널 테이블이 총 4개 존재합니다.

- [ ] **단계 4: 계약 검증 실행**

예상 결과: `ELEVENST_ORDER_ITEM`, `SSG_ORDER_ITEM`, `TOSS_SHOPPING_ORDER_ITEM`만 누락으로 표시됩니다.

- [ ] **단계 5: 커밋**

```powershell
git add sql/channel_orders/005_verify_object_contract.sql sql/channel_orders/020_create_coupang_lotteon_tables.sql
git commit -m "feat: add Coupang and LotteON order tables"
```

### 작업 4: 11번가·SSG 주문상품 테이블 생성

**파일:**
- 생성: `sql/channel_orders/030_create_elevenst_ssg_tables.sql`
- 수정: `sql/channel_orders/005_verify_object_contract.sql`

**인터페이스:**
- 산출물: `dbo.ELEVENST_ORDER_ITEM`, `dbo.SSG_ORDER_ITEM`.

- [ ] **단계 1: 실패하는 필수 컬럼 단언 추가**

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

- [ ] **단계 2: 테이블 생성**

`030_create_elevenst_ssg_tables.sql`을 구현합니다. 외부 표현 형식을 채널이 관리하므로 `OrdItemSeq`, `ShppSeq`, 11번가 주문상품 번호는 `nvarchar(100)`으로 저장합니다. `ScheduledShippingDate`는 `date`, 나머지 원본 시각은 `datetime2(3)`을 사용합니다.

- [ ] **단계 3: 두 번 실행하여 검증**

예상 결과: 총 6개 채널 테이블이 존재하고 계약 검증에서 토스 테이블만 누락으로 표시됩니다.

- [ ] **단계 4: 커밋**

```powershell
git add sql/channel_orders/005_verify_object_contract.sql sql/channel_orders/030_create_elevenst_ssg_tables.sql
git commit -m "feat: add 11st and SSG order tables"
```

### 작업 5: 토스쇼핑 주문상품 테이블 생성

**파일:**
- 생성: `sql/channel_orders/040_create_toss_shopping_table.sql`
- 수정: `sql/channel_orders/005_verify_object_contract.sql`

**인터페이스:**
- 산출물: `OrderProductId`를 논리 키로 사용하는 `dbo.TOSS_SHOPPING_ORDER_ITEM`.

- [ ] **단계 1: 실패하는 토스 컬럼 계약 추가**

다음 컬럼을 필수로 지정합니다:

```text
OrderId, OrderProductId, ProductId, StockId, ProductName, OptionName,
Quantity, Price, OriginPrice, TotalDiscountPrice, TossShoppingDiscount,
TossPayDiscount, TossPayPoint, OrderProductStatus, OrderedAt, CanceledAt,
ConfirmedAt, ShippingDeadlineAt, DeliveryCompanyCode,
ShippingTrackingNumber, DeliveryFeeGroupId, DeliveryFee,
DeliveryLocationType, NormalDeliveryFee, JejuDeliveryFee,
MountainDeliveryFee, ProductManagementCode, ProductItemManagementCode
```

- [ ] **단계 2: 토스 테이블 생성**

`040_create_toss_shopping_table.sql`을 구현합니다. 공식 `int64` 계약에 맞춰 `OrderId`, `OrderProductId`, `ProductId`, `StockId`, `DeliveryFeeGroupId`는 `bigint`를 사용합니다. 원화 정수 금액은 `bigint`, 시각은 `datetime2(3)`을 사용합니다.

주문자·수취인·전화번호·주소 평문 컬럼은 생성하지 않습니다. API에는 있지만 현재 대시보드에는 불필요하므로 `RawJson`에 마스킹된 값으로만 포함합니다.

- [ ] **단계 3: 두 번 실행하고 전체 계약 검증 수행**

예상 결과: 두 DDL 실행이 모두 성공하고 `005_verify_object_contract.sql`이 누락 테이블·컬럼 메시지 없이 정상 종료됩니다.

- [ ] **단계 4: 마스킹된 토스 표본 행 삽입**

트랜잭션 안에서 실행한 뒤 롤백합니다:

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

예상 결과: 삽입이 성공하고 롤백 후 테이블은 비어 있습니다.

- [ ] **단계 5: 커밋**

```powershell
git add sql/channel_orders/005_verify_object_contract.sql sql/channel_orders/040_create_toss_shopping_table.sql
git commit -m "feat: add Toss Shopping order table"
```

### 작업 6: 최신 행·수집 실행·페이로드 인덱스 추가

**파일:**
- 생성: `sql/channel_orders/050_create_channel_order_indexes.sql`
- 생성: `sql/channel_orders/060_verify_history_constraints.sql`

**인터페이스:**
- 입력: 전체 7개 테이블.
- 산출물: 결과가 명확한 최신 행 조회 및 유일성 보장.

- [ ] **단계 1: 실패하는 이력 검증 작성**

각 테이블에 다음 인덱스가 있는지 검사하는 `060_verify_history_constraints.sql`을 생성합니다:

- `IX_<TABLE>_CollectionRunId`
- `IX_<TABLE>_Identity_CollectedAt`
- `WHERE IsLatest = 1` 조건의 필터형 `UX_<TABLE>_Latest`
- `IX_<TABLE>_Identity_PayloadHash`

`sys.indexes`와 `sys.index_columns`를 조회하고 누락 인덱스명과 함께 오류 `51003`을 발생시킵니다. 작업 6 구현 전에는 28개 인덱스를 표시하며 실패해야 합니다.

- [ ] **단계 2: 멱등성을 갖춘 인덱스 생성**

`IF NOT EXISTS` 검사로 `050_create_channel_order_indexes.sql`을 구현합니다. 예시는 다음과 같습니다:

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

설계 명세의 채널별 논리 식별자에 대해 반복합니다.

- [ ] **단계 3: 최신 행 단일성 조건 검증**

롤백할 트랜잭션 안에서 토스 행 하나를 `IsLatest = 1`로 삽입한 뒤 같은 `OrderProductId`와 `IsLatest = 1`을 가진 두 번째 행 삽입을 시도합니다.

예상 결과: SQL Server 오류 `2601` 또는 `2627`이 발생합니다. 첫 행을 `IsLatest = 0`으로 바꾼 후 두 번째 행을 삽입하고, 롤백 전에 최신 행 1개와 전체 이력 행 2개인지 확인합니다.

- [ ] **단계 4: 두 검증 스크립트 실행**

예상 결과: `005_verify_object_contract.sql`과 `060_verify_history_constraints.sql`이 모두 성공합니다.

- [ ] **단계 5: 커밋**

```powershell
git add sql/channel_orders/050_create_channel_order_indexes.sql sql/channel_orders/060_verify_history_constraints.sql
git commit -m "feat: enforce channel order history indexes"
```

### 작업 7: 통합 검증·롤백·운영 문서 추가

**파일:**
- 생성: `sql/channel_orders/090_verify_channel_order_tables.sql`
- 생성: `sql/channel_orders/099_drop_channel_order_tables.sql`
- 생성: `docs/channel-order-tables.md`
- 수정: `SALES_TEAM_ORDER_COLLECTION_STATUS.md`

**인터페이스:**
- 입력: 모든 DDL 및 검증 스크립트.
- 산출물: SSMS 운영자가 반복 실행할 수 있는 배포·복구 지침.

- [ ] **단계 1: 통합 검증 스크립트 생성**

`090_verify_channel_order_tables.sql`은 다음을 수행해야 합니다:

1. SQLCMD `:r` 포함 명령으로 객체·인덱스 검증을 실행합니다.
2. 모든 `RawJson` 검사 제약 조건이 활성화되고 신뢰 상태인지 확인합니다.
3. 트랜잭션 안에서 테이블마다 마스킹 표본을 한 행씩 삽입합니다.
4. 삽입 행 7개와 서로 다른 `CollectionRunId` 7개를 확인합니다.
5. 롤백하고 표본 행이 남아 있지 않은지 확인합니다.

가상 ID만 사용하고 개인정보 필드는 `***`로 처리합니다.

- [ ] **단계 2: 롤백 스크립트 생성**

`099_drop_channel_order_tables.sql`은 명시적인 SQLCMD 변수를 요구해야 합니다:

```sql
:setvar CONFIRM_DROP "NO"
IF N'$(CONFIRM_DROP)' <> N'YES'
    THROW 51009, N'Set CONFIRM_DROP=YES to remove channel order tables.', 1;
```

`IF OBJECT_ID(..., 'U') IS NOT NULL` 검사로 생성의 역순으로 7개 테이블만 삭제합니다. `dbo`와 무관한 ecommerce 객체는 삭제하지 않습니다.

- [ ] **단계 3: 운영 가이드 작성**

다음 내용을 문서화합니다:

- 정확한 실행 순서: `001`, `010`, `020`, `030`, `040`, `050`, `090`.
- SSMS에서 대상 DB를 확인하는 방법.
- 스크립트를 두 번 실행하여 멱등성을 검증하는 방법.
- 트랜잭션 안에서 `IsLatest` 이력을 삽입하는 방법.
- UTC 시각 및 마스킹 규칙.
- 먼저 비운영 테스트 DB에서 `CONFIRM_DROP=YES`로 롤백하는 방법.

- [ ] **단계 4: 현황 문서 갱신**

7개 `dbo.*_ORDER_ITEM` 테이블, 배포 검증 결과, 최신 행 규칙을 정리한 SQL 구현 절을 추가합니다. 실제로 `ecommerce`에 실행하고 검증하지 않았다면 운영 배포가 완료되었다고 기록하지 않습니다.

- [ ] **단계 5: 정적 검사 및 DB 검증**

```powershell
git diff --check
rg -n "stg\.|CREATE SCHEMA|API_KEY|SECRET_KEY|ACCESS_TOKEN" sql docs
```

예상 결과: `stg.` 또는 `CREATE SCHEMA`가 없습니다. 인증 키 이름은 저장 금지를 설명하는 본문에만 나타날 수 있고 실제 값은 포함하지 않습니다. 폐기 가능한 DB 또는 승인된 테스트 DB에서 `090_verify_channel_order_tables.sql`이 성공하는지 확인합니다.

- [ ] **단계 6: 커밋**

```powershell
git add sql/channel_orders docs/channel-order-tables.md SALES_TEAM_ORDER_COLLECTION_STATUS.md
git commit -m "docs: add channel order table deployment guide"
```

## 계획 자체 검토

- 명세 범위: 승인된 7개 채널 테이블, 주문상품당 한 행, 이력 유지, 마스킹 JSON, 인덱스, 검증, 롤백이 모두 작업에 배정되어 있습니다.
- 자리표시자 검사: `TBD`, `TODO`, 미뤄진 구현 단계가 없습니다.
- 자료형 일관성: 공식 토스 `int64` 필드를 제외한 외부 ID는 `nvarchar`이며 공통 메타데이터 이름은 설계 명세와 일치합니다.
- 범위: 공통 정규화 테이블과 대시보드 VIEW는 이 계획에서 제외합니다.
