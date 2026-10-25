# 채널 고유 주문 API 필드 구현 계획

> **에이전트 작업자 안내:** 필수 하위 스킬로 superpowers:subagent-driven-development(권장) 또는 superpowers:executing-plans를 사용하여 이 계획을 작업별로 구현합니다. 진행 상황은 체크박스(`- [ ]`)로 추적합니다.

**목표:** 구현된 7개 채널 API가 반환하는 문서화된 비민감 주문·배송 업무 필드를 자료형이 지정된 채널 고유 SQL 컬럼에 모두 저장하고, 마스킹된 원본 응답과 상태 이력을 유지합니다.

**구조:** 채널당 이력 테이블 하나와 주문상품당 한 행을 유지합니다. 멱등 SQL 마이그레이션으로 기존 테이블을 확장하고 각 어댑터에 새 컬럼을 매핑하며, 저장 컬럼을 원본 API 응답 경로까지 추적할 수 있는 필드 사전을 제공합니다. 공통 대시보드 스키마를 강제하지 않고 채널 고유 개념을 유지합니다.

**기술 스택:** Python 3.12, pytest, Microsoft SQL Server 2017+, T-SQL, `pymssql`, JSON/XML API, Markdown 문서.

## 공통 제약 사항

- 읽기 전용 주문·주문 상세·배송 API만 호출합니다.
- 한 행은 채널 주문상품 하나이며 변경 시 이력을 추가하고 `IsLatest = 1` 행을 하나 유지합니다.
- 기존 테이블과 데이터가 있는 컬럼을 삭제·개명·파괴적 형변환하지 않습니다.
- 새 DDL은 `COL_LENGTH` 검사로 보호된 `ALTER TABLE ... ADD`를 사용하여 멱등성을 보장합니다.
- API 고유 상태 코드와 식별자는 번역하거나 앞자리 0을 잃지 않고 저장합니다.
- 시간대 의미가 확인된 원본 시각은 UTC `datetime2(3)`으로 변환하고 날짜 전용 값은 `date`를 유지합니다.
- API 키, 비밀키, 액세스 토큰, 세션 및 불필요한 개인정보 평문은 저장하지 않습니다.
- `RawJson`은 마스킹을 유지하며 자료형 지정 컬럼을 보완합니다.
- 네이버페이 주문은 고도몰을 통해 수집하고 채널·주문 유입 경로 필드로 구분합니다. 별도 테이블이나 수집기를 만들지 않습니다.
- 공식 계약, 민감정보를 제거한 완전한 표본 또는 검증된 실응답 구조가 뒷받침하는 필드만 추가합니다.

---

### 작업 1: 필드 범위 계약과 마이그레이션 기본 구조 추가

**파일:**
- 생성: `tests/fixtures/channel_field_contracts.json`
- 생성: `tests/test_channel_field_contracts.py`
- 생성: `sql/channel_orders/070_extend_channel_order_api_fields.sql`
- 생성: `sql/channel_orders/075_verify_extended_channel_columns.sql`
- 수정: `src/hmr_order_collection/database.py`

**인터페이스:**
- 입력: 기존 `TABLES: dict[str, TableDefinition]`과 배포된 7개 `dbo.*_ORDER_ITEM` 테이블.
- 산출물: `channel`, `response_path`, `column`, `sql_type`, `nullable`, `classification`, `evidence`를 포함하는 기계 판독용 계약. `classification`은 `stored`, `masked`, `structural`, `transport` 중 하나입니다.

- [ ] **단계 1: 실패하는 계약 테스트 작성**

채널마다 초기 저장 항목 하나를 담은 fixture를 만들고 계약 컬럼이 해당 `TableDefinition`에서 허용되는지 검사합니다:

```python
def test_every_stored_contract_column_is_writable():
    contracts = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    for entry in contracts:
        if entry["classification"] == "stored":
            assert entry["column"] in TABLES[entry["channel"]].columns
```

응답 경로가 비어 있지 않고, 지원되는 분류 및 정확한 SQL 자료형을 사용하며, 근거 값이 `official`, `sample`, `live` 중 하나인지 스키마 검증을 추가합니다.

- [ ] **단계 2: 계약 테스트 실행 및 실패 확인**

실행: `python -m pytest tests/test_channel_field_contracts.py -q`

예상 결과: fixture가 `TABLES`에 없는 새 컬럼을 하나 이상 참조하므로 실패합니다.

- [ ] **단계 3: 조건부 마이그레이션 및 저장 컬럼 추가**

`070_extend_channel_order_api_fields.sql`을 다음과 같이 시작합니다:

```sql
SET NOCOUNT ON;
SET XACT_ABORT ON;

IF COL_LENGTH(N'dbo.NAVER_SMARTSTORE_ORDER_ITEM', N'OrderDate') IS NULL
    ALTER TABLE dbo.NAVER_SMARTSTORE_ORDER_ITEM ADD OrderDate datetime2(3) NULL;
```

네이버 `TableDefinition`에 대응하는 `OrderDate` 항목을 추가합니다. 예상 테이블·컬럼·SQL 자료형을 담은 테이블 변수로 `075_verify_extended_channel_columns.sql`을 만들고 `COL_LENGTH` 또는 `INFORMATION_SCHEMA.COLUMNS`가 일치하지 않으면 오류 `51012`를 발생시킵니다.

- [ ] **단계 4: 대상 테스트 및 SQL 정적 검사 실행**

실행:

```powershell
python -m pytest tests/test_channel_field_contracts.py tests/test_database.py -q
git diff --check
```

예상 결과: 테스트가 통과하고 공백 오류가 없습니다.

- [ ] **단계 5: 커밋**

```powershell
git add tests/fixtures/channel_field_contracts.json tests/test_channel_field_contracts.py sql/channel_orders/070_extend_channel_order_api_fields.sql sql/channel_orders/075_verify_extended_channel_columns.sql src/hmr_order_collection/database.py
git commit -m "test: add channel API field coverage contract"
```

### 작업 2: 네이버 스마트스토어 주문 상세 확장

**파일:**
- 수정: `tests/fixtures/channel_field_contracts.json`
- 수정: `tests/test_naver.py`
- 수정: `src/hmr_order_collection/channels/naver.py`
- 수정: `src/hmr_order_collection/database.py`
- 수정: `sql/channel_orders/070_extend_channel_order_api_fields.sql`
- 수정: `sql/channel_orders/075_verify_extended_channel_columns.sql`

**인터페이스:**
- 입력: `order`, `productOrder`, `delivery` 구역을 가진 네이버 상세 객체.
- 산출물: 해당 구역에서 문서화된 비민감 스칼라 필드 전체의 자료형 지정 컬럼. 구매자·주문자·수취인·연락처·주소·통관 경로는 `masked`로 분류합니다.

- [ ] **단계 1: 네이버 전체 fixture 확장 및 실패 단언 작성**

기존 가상 상세 응답에 최소한 `orderDate`, `paymentMeans`, `payLocationType`, `orderDiscountAmount`, `generalPaymentAmount`, `deliveryFeeAmount`, `sectionDeliveryFee`, `shippingDueDate`, `placeOrderDate`, `placeOrderStatus`, `expectedDeliveryMethod`, `deliveryAttributeType`, `deliveryMethod`, `wrongProductArrival`, `sendDate`, `deliveredDate`를 포함합니다.

예를 들어 다음처럼 실제 매핑 값을 검증합니다:

```python
assert record.columns["OrderDate"] == "2026-08-11T01:02:03+09:00"
assert record.columns["PaymentMeans"] == "CARD"
assert record.columns["PlaceOrderStatus"] == "OK"
assert record.columns["ShippingDueDate"] == "2026-08-12T23:59:59+09:00"
```

- [ ] **단계 2: 네이버 테스트 실행 및 실패 확인**

실행: `python -m pytest tests/test_naver.py tests/test_channel_field_contracts.py -q`

예상 결과: 새 컬럼 키가 없어 실패합니다.

- [ ] **단계 3: 매핑 및 SQL 컬럼 구현**

검증한 필드를 `_map_record`, `TABLES["naver"].columns`, 조건부 마이그레이션, 검증 스크립트, 필드 계약에 추가합니다. `productOrderId`를 유일한 논리 식별자로 유지하고 개인정보 마스킹을 보존합니다.

- [ ] **단계 4: 통과 상태 확인**

실행: `python -m pytest tests/test_naver.py tests/test_database.py tests/test_channel_field_contracts.py -q`

예상 결과: 모든 대상 테스트가 통과합니다.

- [ ] **단계 5: 커밋**

```powershell
git add tests/test_naver.py tests/fixtures/channel_field_contracts.json src/hmr_order_collection/channels/naver.py src/hmr_order_collection/database.py sql/channel_orders/070_extend_channel_order_api_fields.sql sql/channel_orders/075_verify_extended_channel_columns.sql
git commit -m "feat: persist full Naver order detail fields"
```

### 작업 3: 네이버페이 유입 경로를 포함한 고도몰 필드 확장

**파일:**
- 수정: `tests/fixtures/channel_field_contracts.json`
- 수정: `tests/test_godomall.py`
- 수정: `src/hmr_order_collection/channels/godomall.py`
- 수정: `src/hmr_order_collection/database.py`
- 수정: `sql/channel_orders/070_extend_channel_order_api_fields.sql`
- 수정: `sql/channel_orders/075_verify_extended_channel_columns.sql`

**인터페이스:**
- 입력: `Order_Search.php`의 주문 및 `orderGoodsData` 상품 노드.
- 산출물: 고도몰 고유 주문·결제·할인·배송·송장·유입 경로 필드. `orderChannelFl`, `apiOrderNo` 및 제공되는 주문 유형 필드로 같은 테이블 안에서 네이버페이 주문을 구분합니다.

- [ ] **단계 1: 실패하는 네이버페이 주문 유입 경로 매핑 테스트 작성**

민감정보를 제거한 전체 주문 표본에 `orderChannelFl`, `apiOrderNo`, `orderTypeFl`, `settleKind`, `bankSender`, `totalGoodsPrice`, `totalOrderDcPrice`, `totalMemberDcPrice`, `totalCouponGoodsDcPrice`, `totalCouponOrderDcPrice`, `totalMileage`, `totalDeposit`, `orderStatus`, `orderDate`, `paymentDt`와 상품별 `goodsCd`, `goodsPrice`, `optionPrice`, `addGoodsPrice`, `goodsDcPrice`, `couponGoodsDcPrice`, `invoiceCompanySno`, `invoiceNo`, `deliveryDt`를 포함합니다.

네이버페이 fixture가 하나의 `GODOMALL_ORDER_ITEM` 레코드로 유지되고 유입 경로가 보존되는지 확인합니다:

```python
assert record.columns["OrderChannelCode"] == "naverpay"
assert record.columns["ExternalOrderNo"] == "NPAY-0000123"
assert record.columns["OrderTypeCode"] == "order"
```

- [ ] **단계 2: 고도몰 테스트 실행 및 실패 확인**

실행: `python -m pytest tests/test_godomall.py tests/test_channel_field_contracts.py -q`

예상 결과: 확장할 자료형 지정 컬럼이 없어 실패합니다.

- [ ] **단계 3: 전체 주문·상품 매핑 구현**

주문 수준 합계는 각 주문상품 이력 행에 반복 매핑하고 외부 식별자는 문자열로 보존합니다. 고도몰의 특수 날짜 값은 `NULL`로 정규화하며 네이버페이 어댑터나 테이블을 새로 만들지 않습니다.

- [ ] **단계 4: 통과 상태 확인**

실행: `python -m pytest tests/test_godomall.py tests/test_database.py tests/test_channel_field_contracts.py -q`

예상 결과: 모든 대상 테스트가 통과합니다.

- [ ] **단계 5: 커밋**

```powershell
git add tests/test_godomall.py tests/fixtures/channel_field_contracts.json src/hmr_order_collection/channels/godomall.py src/hmr_order_collection/database.py sql/channel_orders/070_extend_channel_order_api_fields.sql sql/channel_orders/075_verify_extended_channel_columns.sql
git commit -m "feat: persist Godomall and Naver Pay origin fields"
```

### 작업 4: 토스쇼핑 자료형 지정 필드 범위 완성

**파일:**
- 수정: `tests/fixtures/channel_field_contracts.json`
- 수정: `tests/test_toss.py`
- 수정: `src/hmr_order_collection/channels/toss.py`
- 수정: `src/hmr_order_collection/database.py`
- 수정: `sql/channel_orders/070_extend_channel_order_api_fields.sql`
- 수정: `sql/channel_orders/075_verify_extended_channel_columns.sql`

**인터페이스:**
- 입력: `/api/v3/shopping-fep/orders/v2`의 토스 주문상품 목록 객체.
- 산출물: 개인정보를 제외한 주문상품 전체 필드의 자료형 지정 컬럼. 주소·이름·전화번호·우편번호·배송 메모는 마스킹을 유지합니다.

- [ ] **단계 1: 실패하는 필드 범위 테스트 작성**

공식 목록 응답의 모든 속성을 담은 전체 fixture를 사용합니다. 기존 금액·할인·배송비·상품 관리·상태·시각·택배사·운송장 필드가 자료형 지정 컬럼으로 유지되는지 확인하고 현재 테이블에 없는 공식 스칼라 필드를 추가합니다.

명시적인 분류 단언을 추가합니다:

```python
private_paths = {entry["response_path"] for entry in contracts if entry["channel"] == "toss" and entry["classification"] == "masked"}
assert "receiverPhone" in private_paths
assert "address" in private_paths
```

- [ ] **단계 2: 토스 테스트 실행 및 문서화된 미분류 필드의 실패 확인**

실행: `python -m pytest tests/test_toss.py tests/test_channel_field_contracts.py -q`

예상 결과: 전체 fixture의 모든 최하위 필드가 저장·마스킹·구조·전송 중 하나로 분류될 때까지 실패합니다.

- [ ] **단계 3: 실제로 누락된 자료형 지정 필드만 추가**

공식 `int64` 식별자와 원화 금액은 `bigint`를 유지합니다. 개인정보 속성을 SQL 평문 컬럼으로 중복 저장하지 않습니다.

- [ ] **단계 4: 통과 상태 확인**

실행: `python -m pytest tests/test_toss.py tests/test_database.py tests/test_channel_field_contracts.py -q`

예상 결과: 모든 대상 테스트가 통과합니다.

- [ ] **단계 5: 커밋**

```powershell
git add tests/test_toss.py tests/fixtures/channel_field_contracts.json src/hmr_order_collection/channels/toss.py src/hmr_order_collection/database.py sql/channel_orders/070_extend_channel_order_api_fields.sql sql/channel_orders/075_verify_extended_channel_columns.sql
git commit -m "feat: complete Toss Shopping field coverage"
```

### 작업 5: 쿠팡 발주서 필드 확장

**파일:**
- 수정: `tests/fixtures/channel_field_contracts.json`
- 수정: `tests/test_coupang.py`
- 수정: `src/hmr_order_collection/channels/coupang.py`
- 수정: `src/hmr_order_collection/database.py`
- 수정: `sql/channel_orders/070_extend_channel_order_api_fields.sql`
- 수정: `sql/channel_orders/075_verify_extended_channel_columns.sql`

**인터페이스:**
- 입력: 문서화된 6개 발주 상태 조회의 배송 묶음 객체와 중첩 `orderItems`.
- 산출물: 출고 상태, 분할 배송, 도서산간 추가 금액, 배송·출고일, 판매자 상품 식별자, 가격, 수수료, 취소 수량, 택배사, 송장 정보를 포함한 배송·상품 필드.

- [ ] **단계 1: 실패하는 배송·상품 필드 단언 작성**

기존 가상 응답에 `orderId`, `orderedAt`, `paidAt`, `status`, `splitShipping`, `remotePrice`, `parcelPrintMessage`, `overseaShippingInfoDto`, 상품별 `vendorItemId`, `sellerProductId`, `sellerProductItemId`, `shippingCount`, `cancelCount`, `holdCountForCancel`, `estimatedShippingDate`, `plannedShippingDate`, `invoiceNumberUploadDate`, `extraProperties` 및 금액 객체를 추가합니다.

개인정보가 아닌 운영 필드는 자료형 지정 컬럼에 저장되고 `orderer`, `receiver`, 세금 증빙의 개인정보 및 해외 개인 식별자는 마스킹되는지 검증합니다.

- [ ] **단계 2: 실패 상태 확인**

실행: `python -m pytest tests/test_coupang.py tests/test_channel_field_contracts.py -q`

예상 결과: 자료형 지정 컬럼이 누락되어 실패합니다.

- [ ] **단계 3: 배송·상품 매핑 및 조건부 DDL 구현**

기존 자리표시자 `SellerProductItemId = None`을 문서화된 상품 속성 매핑으로 수정합니다. `_money`를 통한 중첩 금액 변환과 `nvarchar` 외부 ID를 유지합니다.

- [ ] **단계 4: 통과 상태 확인**

실행: `python -m pytest tests/test_coupang.py tests/test_database.py tests/test_channel_field_contracts.py -q`

예상 결과: 모든 대상 테스트가 통과합니다.

- [ ] **단계 5: 커밋**

```powershell
git add tests/test_coupang.py tests/fixtures/channel_field_contracts.json src/hmr_order_collection/channels/coupang.py src/hmr_order_collection/database.py sql/channel_orders/070_extend_channel_order_api_fields.sql sql/channel_orders/075_verify_extended_channel_columns.sql
git commit -m "feat: persist full Coupang purchase-order fields"
```

### 작업 6: 롯데ON 배송 주문·진행 필드 확장

**파일:**
- 수정: `tests/fixtures/channel_field_contracts.json`
- 수정: `tests/test_lotteon.py`
- 수정: `src/hmr_order_collection/channels/lotteon.py`
- 수정: `src/hmr_order_collection/database.py`
- 수정: `sql/channel_orders/070_extend_channel_order_api_fields.sql`
- 수정: `sql/channel_orders/075_verify_extended_channel_columns.sql`

**인터페이스:**
- 입력: `odNo + odSeq`로 결합한 `SellerDeliveryOrdersSearch`와 `SellerDeliveryProgressStateSearch` 행.
- 산출물: 두 API의 비개인정보 주문·상품·수량·금액·배송 지시·진행·택배사·송장·이벤트 시각 필드 전체.

- [ ] **단계 1: 실패하는 두 응답 결합 테스트 작성**

공식 계약 또는 실응답에서 확인한 모든 스칼라 업무 필드로 민감정보를 제거한 주문·진행 fixture를 확장합니다. 주문 값과 최신 `dvTrcStatDttm`의 진행 값이 하나의 레코드에 함께 존재하고, 원본 JSON은 `deliveryOrder`와 `deliveryProgress`를 별도 객체로 유지하는지 검증합니다.

- [ ] **단계 2: 실패 상태 확인**

실행: `python -m pytest tests/test_lotteon.py tests/test_channel_field_contracts.py -q`

예상 결과: 진행 및 업무 컬럼이 누락되어 실패합니다.

- [ ] **단계 3: 매핑·자료형·마이그레이션 구현**

식별자별 최신 진행 이벤트를 선택하는 동작을 유지합니다. `_PRIVATE_FIELDS`의 모든 필드를 마스킹 대상으로 분류하고 SQL 평문 컬럼으로 추가하지 않습니다.

- [ ] **단계 4: 통과 상태 확인**

실행: `python -m pytest tests/test_lotteon.py tests/test_database.py tests/test_channel_field_contracts.py -q`

예상 결과: 모든 대상 테스트가 통과합니다.

- [ ] **단계 5: 커밋**

```powershell
git add tests/test_lotteon.py tests/fixtures/channel_field_contracts.json src/hmr_order_collection/channels/lotteon.py src/hmr_order_collection/database.py sql/channel_orders/070_extend_channel_order_api_fields.sql sql/channel_orders/075_verify_extended_channel_columns.sql
git commit -m "feat: persist full LotteON delivery fields"
```

### 작업 7: 검증된 SSG 배송 단계 API 전체 결합

**파일:**
- 수정: `tests/fixtures/channel_field_contracts.json`
- 수정: `tests/test_ssg.py`
- 수정: `src/hmr_order_collection/channels/ssg.py`
- 수정: `src/hmr_order_collection/database.py`
- 수정: `sql/channel_orders/070_extend_channel_order_api_fields.sql`
- 수정: `sql/channel_orders/075_verify_extended_channel_columns.sql`

**인터페이스:**
- 입력: `listShppDirection.ssg`, `listWarehouseOut.ssg`, `listNonDelivery.ssg`, `listDeliveryEnd.ssg` 응답.
- 산출물: `OrdNo + OrdItemSeq + ShppNo + ShppSeq`당 하나의 SSG 이력 레코드. 성공적으로 반환된 비개인정보 주문 지시·출고·배송 중·배송 완료 필드를 모두 포함합니다.

- [ ] **단계 1: 실패하는 엔드포인트 결합 테스트 작성**

4개 엔드포인트의 응답 구조에 대한 민감정보 제거 fixture를 추가합니다. 식별자가 같으면 상태 코드·예정일·실제 출고/발송 시각·택배사·송장·배송 진행·배송 완료 시각이 하나의 레코드로 합쳐지는지 검증합니다. `listNonDelivery.ssg`의 업무 오류 `resultCode=99`가 조용히 0건 처리되지 않고 명시적인 부분 수집 오류를 발생시키는지 테스트합니다.

- [ ] **단계 2: 실패 상태 확인**

실행: `python -m pytest tests/test_ssg.py tests/test_channel_field_contracts.py -q`

예상 결과: 현재 어댑터가 `listShppDirection.ssg`만 호출하므로 실패합니다.

- [ ] **단계 3: 읽기 전용 호출 및 식별자 결합 구현**

문서화된 요청 구조로 4개 엔드포인트를 호출합니다. 성공 응답만 결합하고 알려진 미배송 API 권한·업무 오류는 부분 실행 실패로 드러내어 DB 트랜잭션이 전체 수집 완료로 처리되지 않게 합니다.

- [ ] **단계 4: 통과 상태 확인**

실행: `python -m pytest tests/test_ssg.py tests/test_database.py tests/test_channel_field_contracts.py -q`

예상 결과: 모든 대상 테스트가 통과합니다.

- [ ] **단계 5: 커밋**

```powershell
git add tests/test_ssg.py tests/fixtures/channel_field_contracts.json src/hmr_order_collection/channels/ssg.py src/hmr_order_collection/database.py sql/channel_orders/070_extend_channel_order_api_fields.sql sql/channel_orders/075_verify_extended_channel_columns.sql
git commit -m "feat: collect full SSG shipping lifecycle fields"
```

### 작업 8: 지원 근거가 없는 필드를 만들지 않고 검증된 11번가 응답 확장

**파일:**
- 수정: `tests/fixtures/channel_field_contracts.json`
- 수정: `tests/test_elevenst.py`
- 수정: `src/hmr_order_collection/channels/elevenst.py`
- 수정: `src/hmr_order_collection/database.py`
- 수정: `sql/channel_orders/070_extend_channel_order_api_fields.sql`
- 수정: `sql/channel_orders/075_verify_extended_channel_columns.sql`

**인터페이스:**
- 입력: 검증된 `complete`, `shipping` XML 응답.
- 산출물: 두 응답의 비개인정보 스칼라 필드 전체에 대한 자료형 지정 컬럼. 식별자가 겹치면 우선순위가 높은 배송 레코드를 사용합니다.

- [ ] **단계 1: 네임스페이스를 포함한 전체 XML 실패 테스트 작성**

검증된 두 응답의 전체 XML 노드에서 민감정보를 제거하여 사용합니다. 주문·상품 식별자, 수량, 금액, 상태 코드, 주문·결제·발송일, 택배사, 송장, 판매자 관리 코드, 배송비를 포함합니다. 네임스페이스 제거와 상태 우선순위 적용 후 정확한 값을 확인합니다.

- [ ] **단계 2: 실패 상태 확인**

실행: `python -m pytest tests/test_elevenst.py tests/test_channel_field_contracts.py -q`

예상 결과: 검증되었지만 자료형 지정 컬럼이 없는 필드로 인해 실패합니다.

- [ ] **단계 3: 검증된 매핑만 구현**

이전에 `500/-997`을 반환한 미검증 엔드포인트의 컬럼은 추가하지 않습니다. 개인정보 XML 경로는 마스킹, 응답 외곽 구조는 구조·전송 항목으로 분류합니다.

- [ ] **단계 4: 통과 상태 확인**

실행: `python -m pytest tests/test_elevenst.py tests/test_database.py tests/test_channel_field_contracts.py -q`

예상 결과: 모든 대상 테스트가 통과합니다.

- [ ] **단계 5: 커밋**

```powershell
git add tests/test_elevenst.py tests/fixtures/channel_field_contracts.json src/hmr_order_collection/channels/elevenst.py src/hmr_order_collection/database.py sql/channel_orders/070_extend_channel_order_api_fields.sql sql/channel_orders/075_verify_extended_channel_columns.sql
git commit -m "feat: persist complete verified 11st feed fields"
```

### 작업 9: 필드 사전 생성 및 안전한 배포 검증

**파일:**
- 생성: `src/hmr_order_collection/field_dictionary.py`
- 생성: `tests/test_field_dictionary.py`
- 생성: `docs/channel-api-field-dictionary.md`
- 수정: `docs/channel-order-tables.md`
- 수정: `SALES_TEAM_ORDER_COLLECTION_STATUS.md`

**인터페이스:**
- 입력: `tests/fixtures/channel_field_contracts.json` 및 배포된 SQL 메타데이터.
- 산출물: 채널별로 API, 응답 경로, DB 테이블·컬럼, SQL 자료형, NULL 허용 여부, 설명·의미, 변환, 근거를 정리한 일정한 결과의 Markdown 문서.

- [ ] **단계 1: 실패하는 출력 일관성 테스트 작성**

```python
def test_render_field_dictionary_is_grouped_and_stable():
    rendered = render_field_dictionary(CONTRACT_PATH)
    assert rendered.startswith("# 채널별 주문·배송 API 필드 사전\n")
    assert "## 네이버 스마트스토어" in rendered
    assert "## 한촌몰·고도몰(네이버페이 포함)" in rendered
    assert rendered.index("## 네이버 스마트스토어") < rendered.index("## 토스쇼핑")
```

- [ ] **단계 2: 실패 상태 확인**

실행: `python -m pytest tests/test_field_dictionary.py -q`

예상 결과: `field_dictionary.py`가 없어 실패합니다.

- [ ] **단계 3: 렌더러 구현 및 문서 생성**

채널·컬럼 순서를 고정한 `render_field_dictionary(path: Path) -> str`을 구현합니다. `docs/channel-api-field-dictionary.md`를 생성하고 마이그레이션 순서가 `070` 다음 `075`임을 문서화하며 네이버페이가 `GODOMALL_ORDER_ITEM`에 포함됨을 명시합니다.

- [ ] **단계 4: 전체 로컬 검증 실행**

실행:

```powershell
python -m pytest -q
git diff --check
rg -n "access_token|client_secret|secret_key|partner_key|user_key" docs/channel-api-field-dictionary.md sql/channel_orders/070_extend_channel_order_api_fields.sql
```

예상 결과: 모든 테스트가 통과하고 비밀정보 값이나 인증 컬럼이 없습니다.

- [ ] **단계 5: 승인된 ecommerce DB에서 SQL 검증 실행**

`.env`에서 읽은 인증 정보를 출력하지 않고 사용하여 `070_extend_channel_order_api_fields.sql`, `075_verify_extended_channel_columns.sql` 순으로 실행합니다. `070`을 다시 실행한 뒤 `075`도 다시 실행합니다.

예상 결과: 마이그레이션 두 번이 모두 성공하고 매번 검증이 통과하며 기존 행 수는 바뀌지 않습니다.

- [ ] **단계 6: 커밋**

```powershell
git add src/hmr_order_collection/field_dictionary.py tests/test_field_dictionary.py docs/channel-api-field-dictionary.md docs/channel-order-tables.md SALES_TEAM_ORDER_COLLECTION_STATUS.md sql/channel_orders tests/fixtures/channel_field_contracts.json
git commit -m "docs: publish channel API field dictionary"
```

## 계획 자체 검토

- 명세 범위: 구현된 7개 채널, 고도몰을 통한 네이버페이, 채널 고유 자료형 지정 컬럼, 마스킹 JSON, API 결합, 안전한 마이그레이션, 이력 보존, 필드 추적 및 검증이 모두 명시적 작업에 포함됩니다.
- 범위: 공통 대시보드 뷰, 정규화 상태, 알림 규칙, 정산·광고·재고 영역 및 미승인 채널은 제외합니다.
- 자료형 일관성: `int64`를 보장하는 토스 필드를 제외한 외부 쇼핑몰 ID는 문자열이며, 시각은 `datetime2(3)`, 날짜 전용 값은 `date`입니다.
- 테스트 주도 개발: 모든 운영 코드 변경은 대상 동작의 실패 테스트로 시작하고 실패·통과를 확인하는 명령을 포함합니다.
- 자리표시자 검사: 미뤄진 구현 표시가 없으며 새 응답 필드는 코드 승인 전에 저장·마스킹·구조·전송 계약으로 명시해야 합니다.
