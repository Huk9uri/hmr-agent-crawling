# HMR 판매채널 주문 수집 테이블 정의서

- 작성일: 2026-09-18
- 기준 버전: `HMR_Agent_Crawling_v1.0.0_20260918` / `main` 커밋 `3731e7a`
- DBMS: Microsoft SQL Server
- 스키마: `dbo`
- 기준 DDL: `sql/channel_orders/010`~`080`, 확장 컬럼 `070`, 인덱스 `050`

## 1. 데이터 모델 개요

| 구분 | 테이블 | 용도 | 논리 식별키 |
|---|---|---|---|
| 주문 이력 | `NAVER_SMARTSTORE_ORDER_ITEM` | 네이버 스마트스토어 상품주문 이력 | `ProductOrderId` |
| 주문 이력 | `COUPANG_ORDER_ITEM` | 쿠팡 주문상품 이력 | `ShipmentBoxId`, `OrderItemId` |
| 주문 이력 | `GODOMALL_ORDER_ITEM` | 고도몰·네이버페이·페이코 주문상품 이력 | `OrderNo`, `OrderItemSno` |
| 주문 이력 | `LOTTEON_ORDER_ITEM` | 롯데ON 주문상품 이력 | `OrderNo`, `OrderItemSeq` |
| 주문 이력 | `ELEVENST_ORDER_ITEM` | 11번가 주문상품 이력 | `OrderNo`, `OrderProductNo` |
| 주문 이력 | `SSG_ORDER_ITEM` | SSG 배송 단위 주문상품 이력 | `OrdNo`, `OrdItemSeq`, `ShppNo`, `ShppSeq` |
| 주문 이력 | `CJ_ONSTYLE_ORDER_ITEM` | CJ온스타일 주문 처리 단위 이력 | `OrderNo`, `OrderItemSequence`, `OrderDetailSequence`, `OrderProcessingSequence` |
| 주문 이력 | `TOSS_SHOPPING_ORDER_ITEM` | 토스쇼핑 주문상품 이력 | `OrderProductId` |
| 주문 이력 | `KAKAO_SHOPPING_ORDER_ITEM` | 톡스토어·선물하기 주문 이력 | `ChannelType`, `OrderId` |
| 감사 | `CHANNEL_COLLECTION_RUN` | 일일 수집 실행 단위 | `RunId` |
| 감사 | `CHANNEL_COLLECTION_ATTEMPT` | 실행 내 채널별 시도 단위 | `RunId`, `ChannelName`, `AttemptNo` |

주문 테이블은 현재값 덮어쓰기가 아닌 이력 추가 방식이다. 동일 논리 식별키에서 `IsLatest=1`인 행은 필터형 UNIQUE 인덱스로 하나만 허용한다. `CollectedAt`, `CreatedAt` 등 시스템 시각은 UTC 기준이며 화면·보고서에서 KST로 변환한다.

## 2. 주문 이력 공통 컬럼

카카오쇼핑을 제외한 기존 채널은 `SourceCreatedAt`, `SourceModifiedAt`을 기본 공통 컬럼으로 가진다. 카카오쇼핑은 대응되는 원본 시각을 `OrderedAt`, `ModifiedAt`으로 저장한다.

| 컬럼 | 형식 | NULL | 키·기본값 | 설명 |
|---|---|---:|---|---|
| `StagingId` | `bigint IDENTITY(1,1)` | N | PK | 이력 행 대체키 |
| `CollectionRunId` | `uniqueidentifier` | N | 실행 식별자 | 해당 적재 작업의 실행 ID |
| `CollectedAt` | `datetime2(3)` | N |  | API 수집 시각(UTC) |
| `SourceCreatedAt` | `datetime2(3)` | Y |  | 원천 데이터 생성 시각 |
| `SourceModifiedAt` | `datetime2(3)` | Y |  | 원천 데이터 최종 변경 시각 |
| `RawOrderStatus` | `nvarchar(100)` | Y |  | 채널 원본 주문 상태 |
| `RawDeliveryStatus` | `nvarchar(100)` | Y |  | 채널 원본 배송 상태 |
| `RawJson` | `nvarchar(max)` | N | `ISJSON=1` | 개인정보를 마스킹한 원본 JSON |
| `PayloadHash` | `binary(32)` | N | SHA-256 | 동일 내용 중복 적재 판정값 |
| `IsLatest` | `bit` | N | 기본값 `1` | 논리키별 최신 행 여부 |
| `CreatedAt` | `datetime2(3)` | N | `SYSUTCDATETIME()` | DB 행 생성 시각 |

## 3. 채널별 테이블

### 3.1 `NAVER_SMARTSTORE_ORDER_ITEM`

| 컬럼 | 형식 | NULL | 설명 |
|---|---|---:|---|
| `ProductOrderId` | `nvarchar(100)` | N | 네이버 상품주문 ID, 논리 식별키 |
| `OrderId` | `nvarchar(100)` | Y | 주문 ID |
| `ProductId`, `OptionId` | `nvarchar(100)` | Y | 상품·옵션 ID |
| `ProductName`, `OptionName` | `nvarchar(500)` | Y | 상품·옵션명 |
| `Quantity` | `int` | Y | 주문수량, 0 이상 제약 |
| `UnitPrice` | `decimal(19,4)` | Y | 단가 |
| `TotalPaymentAmount` | `decimal(19,4)` | Y | 총 결제금액 |
| `OrderDiscountAmount`, `GeneralPaymentAmount` | `decimal(19,4)` | Y | 주문할인·일반결제 금액 |
| `DeliveryFeeAmount`, `SectionDeliveryFee` | `decimal(19,4)` | Y | 배송비·구간 배송비 |
| `ProductOrderStatus`, `ClaimStatus`, `DeliveryStatus` | `nvarchar(100)` | Y | 상품주문·클레임·배송 상태 |
| `PaymentMeans`, `PayLocationType` | `nvarchar(100)` | Y | 결제수단·결제 위치 유형 |
| `OptionManageCode` | `nvarchar(100)` | Y | 옵션 관리코드 |
| `OrderDate`, `PaymentAt`, `PlaceOrderDate` | `datetime2(3)` | Y | 주문·결제·발주 시각 |
| `ShippingDueDate`, `DispatchAt`, `DeliveryCompletedAt` | `datetime2(3)` | Y | 발송기한·발송·배송완료 시각 |
| `PlaceOrderStatus`, `ExpectedDeliveryMethod`, `DeliveryAttributeType`, `DeliveryMethod` | `nvarchar(100)` | Y | 발주·배송 방법 관련 값 |
| `DeliveryCompanyCode`, `TrackingNumber` | `nvarchar(100)` | Y | 택배사 코드·송장번호 |

### 3.2 `COUPANG_ORDER_ITEM`

| 컬럼 | 형식 | NULL | 설명 |
|---|---|---:|---|
| `ShipmentBoxId`, `OrderItemId` | `nvarchar(100)` | N | 배송박스·주문상품 ID, 복합 논리키 |
| `OrderId`, `VendorItemId`, `SellerProductId`, `SellerProductItemId`, `ProductId` | `nvarchar(100)` | Y | 주문 및 상품 식별자 |
| `VendorItemPackageId` | `nvarchar(100)` | Y | 판매상품 패키지 ID |
| `VendorItemPackageName`, `VendorItemName` | `nvarchar(500)` | Y | 패키지·판매상품명 |
| `ProductName`, `OptionName` | `nvarchar(500)` | Y | 상품·옵션명 |
| `Quantity`, `CanceledQuantity`, `HeldCancellationQuantity` | `int` | Y | 주문·취소·취소보류 수량 |
| `SalesPrice` | `decimal(19,4)` | Y | 판매금액 |
| `SalesPriceCurrencyCode` | `nvarchar(100)` | Y | 판매금액 통화코드 |
| `OrderStatus`, `DeliveryStatus` | `nvarchar(100)` | Y | 주문·배송 상태 |
| `OrderedAt`, `PaidAt`, `EstimatedShippingAt`, `DispatchedAt`, `DeliveryCompletedAt` | `datetime2(3)` | Y | 주문·결제·예정발송·발송·완료 시각 |
| `DeliveryCompanyCode`, `TrackingNumber` | `nvarchar(100)` | Y | 택배사 코드·송장번호 |

### 3.3 `GODOMALL_ORDER_ITEM`

| 컬럼 | 형식 | NULL | 설명 |
|---|---|---:|---|
| `OrderNo`, `OrderItemSno` | `nvarchar(100)` | N | 주문번호·주문상품 순번, 복합 논리키 |
| `OrderChannelCode`, `ExternalOrderNo` | `nvarchar(100)` | Y | `shop`, `naverpay`, `payco` 등 채널·외부 주문번호 |
| `ProductCode`, `OptionCode` | `nvarchar(100)` | Y | 상품·옵션 코드 |
| `ProductName`, `OptionName` | `nvarchar(500)` | Y | 상품·옵션명 |
| `Quantity` | `int` | Y | 주문수량 |
| `UnitPrice`, `OptionPrice`, `AdditionalGoodsPrice` | `decimal(19,4)` | Y | 단가·옵션가·추가상품 금액 |
| `PaymentAmount`, `DiscountAmount`, `DeliveryFee` | `decimal(19,4)` | Y | 결제·할인·배송 금액 |
| `GoodsDiscountAmount`, `CouponGoodsDiscountAmount`, `TotalGoodsPrice` | `decimal(19,4)` | Y | 상품할인·상품쿠폰·상품합계 |
| `OrderDiscountAmount`, `MemberDiscountAmount`, `CouponOrderDiscountAmount` | `decimal(19,4)` | Y | 주문·회원·주문쿠폰 할인 |
| `UsedMileageAmount`, `UsedDepositAmount` | `decimal(19,4)` | Y | 사용 마일리지·예치금 |
| `OrderTypeCode`, `SettlementMethodCode` | `nvarchar(100)` | Y | 주문 유형·결제수단 코드 |
| `OrderStatus`, `PaymentStatus`, `DeliveryStatus` | `nvarchar(100)` | Y | 주문·결제·배송 상태 |
| `OrderedAt`, `PaidAt`, `DispatchedAt` | `datetime2(3)` | Y | 주문·결제·발송 시각 |
| `DeliveryCompanyCode`, `TrackingNumber` | `nvarchar(100)` | Y | 택배사 코드·송장번호 |

### 3.4 `LOTTEON_ORDER_ITEM`

| 컬럼 | 형식 | NULL | 설명 |
|---|---|---:|---|
| `OrderNo`, `OrderItemSeq` | `nvarchar(100)` | N | 주문번호·주문상품 순번, 복합 논리키 |
| `ProcessSequence` | `nvarchar(100)` | Y | 주문 처리 순번 |
| `ProductId`, `OptionId` | `nvarchar(100)` | Y | 상품·옵션 ID |
| `ProductName`, `OptionName` | `nvarchar(500)` | Y | 상품·옵션명 |
| `Quantity`, `CanceledQuantity` | `int` | Y | 주문·취소 수량 |
| `SalesAmount`, `PaymentAmount` | `decimal(19,4)` | Y | 판매·결제 금액 |
| `OrderStatus`, `DeliveryStatus` | `nvarchar(100)` | Y | 주문·배송 상태 |
| `OrderedAt`, `PaidAt`, `DispatchedAt`, `DeliveryCompletedAt` | `datetime2(3)` | Y | 주문·결제·발송·배송완료 시각 |
| `DeliveryCompanyCode`, `TrackingNumber` | `nvarchar(100)` | Y | 택배사 코드·송장번호 |

### 3.5 `ELEVENST_ORDER_ITEM`

| 컬럼 | 형식 | NULL | 설명 |
|---|---|---:|---|
| `OrderNo`, `OrderProductNo` | `nvarchar(100)` | N | 주문번호·주문상품번호, 복합 논리키 |
| `ProductId`, `OptionId` | `nvarchar(100)` | Y | 상품·옵션 ID |
| `ProductName`, `OptionName` | `nvarchar(500)` | Y | 상품·옵션명 |
| `Quantity` | `int` | Y | 주문수량 |
| `OrderAmount` | `decimal(19,4)` | Y | 주문금액 |
| `OrderStatus`, `DeliveryStatus` | `nvarchar(100)` | Y | 주문·배송 상태 |
| `OrderedAt`, `PaidAt`, `DispatchedAt` | `datetime2(3)` | Y | 주문·결제·발송 시각 |
| `DeliveryCompanyCode`, `TrackingNumber` | `nvarchar(100)` | Y | 택배사 코드·송장번호 |

### 3.6 `SSG_ORDER_ITEM`

| 컬럼 | 형식 | NULL | 설명 |
|---|---|---:|---|
| `OrdNo`, `OrdItemSeq`, `ShppNo`, `ShppSeq` | `nvarchar(100)` | N | 주문·상품·배송번호와 순번, 복합 논리키 |
| `SiteNo`, `ItemId`, `UitemId`, `SplVenItemId`, `USplVenItemId` | `nvarchar(100)` | Y | 사이트·상품·단품·협력업체 상품 식별자 |
| `ItemName`, `UnitItemName` | `nvarchar(500)` | Y | 상품·단품명 |
| `OrderQuantity`, `DirectedQuantity`, `CanceledQuantity` | `int` | Y | 주문·지시·취소 수량 |
| `SupplyPrice`, `SalesPrice`, `RealOrderAmount`, `DiscountAmount` | `decimal(19,4)` | Y | 공급가·판매가·실결제·할인 금액 |
| `OrderStatusCode`, `ShippingStatusCode`, `ShippingProgressDetailCode` | `nvarchar(100)` | Y | 주문·배송·배송상세 상태코드 |
| `OrderReceivedAt`, `OrderCompletedAt`, `WarehouseOutCompletedAt` | `datetime2(3)` | Y | 주문접수·주문완료·출고완료 시각 |
| `ScheduledShippingDate` | `date` | Y | 출고 예정일 |
| `DeliveryTrackingStatusAt`, `DeliveryCompletedAt` | `datetime2(3)` | Y | 배송추적 상태·배송완료 시각 |
| `DeliveryCompanyCode`, `TrackingNumber` | `nvarchar(100)` | Y | 택배사 코드·송장번호 |

### 3.7 `CJ_ONSTYLE_ORDER_ITEM`

| 컬럼 | 형식 | NULL | 설명 |
|---|---|---:|---|
| `OrderNo`, `OrderItemSequence`, `OrderDetailSequence`, `OrderProcessingSequence` | `nvarchar(100)` | N | 주문 처리 단위 복합 논리키 |
| `OriginalOrderNo` | `nvarchar(100)` | Y | 원주문번호 |
| `ItemCode`, `OptionCode`, `VendorItemCode` | `nvarchar(100)` | Y | 상품·옵션·협력사 상품코드 |
| `ItemName`, `OptionName`, `WebItemName`, `PackItemName` | `nvarchar(500)` | Y | 상품·옵션·웹·묶음상품명 |
| `PackItemAvailability`, `ItemType`, `ItemCategory` | `nvarchar(100)` | Y | 묶음상품 여부·상품 유형·분류 |
| `Quantity` | `int` | Y | 수량 |
| `SupplyPrice`, `SalesPrice`, `PaymentPrice`, `CustomerResponsibilityCost` | `decimal(19,4)` | Y | 공급·판매·결제·고객부담 금액 |
| `DeliveryStatus`, `DeliveryInstructionCheck`, `DeliveryType`, `OrderType`, `ScheduledCancellation` | `nvarchar(100)` | Y | 주문·배송 처리 상태 |
| `DeliveryMethodName` | `nvarchar(500)` | Y | 배송방법명 |
| `DeliveryInstructionAt`, `DispatchedAt`, `DeliveryCompletedAt`, `DeliveryCanceledAt`, `PaidAt` | `datetime2(3)` | Y | 배송지시·발송·완료·취소·결제 시각 |
| `ExpectedDeliveryDate` | `date` | Y | 배송 예정일 |
| `DeliveryCompanyCode`, `TrackingNumber`, `WaybillIdentifierNo` | `nvarchar(100)` | Y | 택배사·송장·운송장 식별번호 |
| `ReasonForNonDelivery`, `ClaimReason` | `nvarchar(500)` | Y | 미배송·클레임 사유 |
| `SalesChannel` | `nvarchar(100)` | Y | 판매채널 코드 |
| `SalesChannelName`, `AffiliateItemName`, `BrandName`, `FulfillmentName` | `nvarchar(500)` | Y | 판매채널·제휴상품·브랜드·풀필먼트명 |
| `EarlyMorningDelivery`, `AlreadyDeliveryStatus`, `ForcedDeliveryStatus`, `CustomerDesignationStatus`, `InternationalShippingAvailability` | `nvarchar(100)` | Y | 배송 관련 구분값 |
| `AffiliateItemCode`, `BrandCode` | `nvarchar(100)` | Y | 제휴상품·브랜드 코드 |

### 3.8 `TOSS_SHOPPING_ORDER_ITEM`

| 컬럼 | 형식 | NULL | 설명 |
|---|---|---:|---|
| `OrderId` | `bigint` | N | 주문 ID |
| `OrderProductId` | `bigint` | N | 주문상품 ID, 논리 식별키 |
| `ProductId`, `StockId` | `bigint` | Y | 상품·재고 ID |
| `ProductName`, `OptionName` | `nvarchar(500)` | Y | 상품·옵션명 |
| `Quantity` | `int` | Y | 주문수량 |
| `Price`, `OriginPrice`, `TotalDiscountPrice` | `bigint` | Y | 판매가·정상가·총 할인액 |
| `TossShoppingDiscount`, `TossPayDiscount`, `TossPayPoint` | `bigint` | Y | 토스 부담 할인·포인트 |
| `OrderProductStatus` | `nvarchar(100)` | Y | 주문상품 상태 |
| `OrderedAt`, `CanceledAt`, `ConfirmedAt`, `ShippingDeadlineAt` | `datetime2(3)` | Y | 주문·취소·구매확정·발송기한 시각 |
| `DeliveryCompanyCode`, `ShippingTrackingNumber` | `nvarchar(100)` | Y | 택배사 코드·송장번호 |
| `DeliveryFeeGroupId`, `DeliveryFee`, `NormalDeliveryFee`, `JejuDeliveryFee`, `MountainDeliveryFee` | `bigint` | Y | 배송비 정책·지역별 배송비 |
| `DeliveryLocationType` | `nvarchar(100)` | Y | 배송지역 유형 |
| `ProductManagementCode`, `ProductItemManagementCode` | `nvarchar(100)` | Y | 상품·옵션 관리코드 |

### 3.9 `KAKAO_SHOPPING_ORDER_ITEM`

이 테이블에는 `SourceCreatedAt`, `SourceModifiedAt`이 없고, 원본 생성·변경 시각을 `OrderedAt`, `ModifiedAt`으로 보관한다.

| 컬럼 | 형식 | NULL | 설명 |
|---|---|---:|---|
| `ChannelType`, `OrderId` | `nvarchar(100)` | N | 톡스토어·선물하기 구분과 주문 ID, 복합 논리키 |
| `PaymentId`, `ProductId`, `SellerItemNo`, `SellerItemOptionCode` | `nvarchar(100)` | Y | 결제·상품·판매자 관리 식별자 |
| `ProductName`, `OptionName` | `nvarchar(500)` | Y | 상품·옵션명 |
| `Quantity` | `int` | Y | 주문수량 |
| `ProductPrice`, `OptionPrice` | `decimal(19,4)` | Y | 상품·옵션 금액 |
| `SellerDiscountPrice`, `SellerCouponDiscountPrice`, `AdminDiscountPrice` | `decimal(19,4)` | Y | 판매자·쿠폰·관리자 할인액 |
| `SettlementBasicPrice`, `DeliveryAmount`, `AreaAdditionalDeliveryAmount` | `decimal(19,4)` | Y | 정산기준·배송·지역추가 배송비 |
| `OrderStatus` | `nvarchar(100)` | Y | 주문 상태 |
| `OrderedAt`, `PaidAt`, `ModifiedAt` | `datetime2(3)` | Y | 주문·결제·최종변경 시각 |
| `DeliveryRequestAt`, `ConfirmedAt`, `InvoiceRegisteredAt`, `DeliveryCompletedAt` | `datetime2(3)` | Y | 배송요청·확인·송장등록·완료 시각 |
| `ShippingMethod`, `DeliveryCompanyCode`, `TrackingNumber` | `nvarchar(100)` | Y | 배송방법·택배사·송장번호 |
| `CancelClaimStatus`, `ExchangeClaimStatus`, `ReturnClaimStatus` | `nvarchar(100)` | Y | 취소·교환·반품 최종 상태 |

## 4. 감사 테이블

### 4.1 `CHANNEL_COLLECTION_RUN`

| 컬럼 | 형식 | NULL | 키·기본값 | 설명 |
|---|---|---:|---|---|
| `RunId` | `uniqueidentifier` | N | PK | 일일 수집 실행 ID |
| `ScheduledDate` | `date` | N |  | 기준 실행일 |
| `StartedAt` | `datetime2(3)` | N |  | 실행 시작 시각 |
| `FinishedAt` | `datetime2(3)` | Y |  | 실행 종료 시각 |
| `RunStatus` | `nvarchar(30)` | N |  | 실행 상태 |
| `SuccessfulChannels` | `int` | N | 기본값 `0` | 성공 채널 수 |
| `FailedChannels` | `int` | N | 기본값 `0` | 실패 채널 수 |
| `CreatedAt` | `datetime2(3)` | N | `SYSUTCDATETIME()` | 감사 행 생성 시각 |

인덱스: `IX_CHANNEL_COLLECTION_RUN_SCHEDULED_STATUS(ScheduledDate, RunStatus)`

### 4.2 `CHANNEL_COLLECTION_ATTEMPT`

| 컬럼 | 형식 | NULL | 키·제약 | 설명 |
|---|---|---:|---|---|
| `AttemptId` | `bigint IDENTITY(1,1)` | N | PK | 채널 시도 대체키 |
| `RunId` | `uniqueidentifier` | N | FK → `CHANNEL_COLLECTION_RUN.RunId` | 상위 실행 ID |
| `ChannelName` | `nvarchar(30)` | N | UQ 구성 | 채널 코드 |
| `AttemptNo` | `int` | N | UQ 구성 | 실행 내 시도 번호 |
| `StartedAt`, `FinishedAt` | `datetime2(3)` | N |  | 시도 시작·종료 시각 |
| `AttemptStatus` | `nvarchar(30)` | N |  | `SUCCESS`, `SUCCESS_EMPTY`, 실패 상태 등 |
| `WindowsCount` | `int` | N |  | 호출한 날짜 구간 수 |
| `PagesCount` | `int` | N |  | 조회한 API 페이지 수 |
| `RecordsCount` | `int` | N |  | 수집 레코드 수 |
| `InsertedCount` | `int` | N |  | 신규 이력 삽입 수 |
| `ChangedCount` | `int` | N |  | 내용 변경 수 |
| `SkippedCount` | `int` | N |  | 동일 payload로 건너뛴 수 |
| `ErrorCategory` | `nvarchar(50)` | Y |  | 실패 분류 |

- UNIQUE: `(RunId, ChannelName, AttemptNo)`
- 인덱스: `IX_CHANNEL_COLLECTION_ATTEMPT_CHANNEL_STATUS(ChannelName, AttemptStatus, FinishedAt)`

## 5. 주문 테이블 공통 인덱스 정책

각 주문 테이블에는 아래 네 종류의 인덱스를 둔다.

1. `CollectionRunId` 조회 인덱스
2. 논리 식별키와 `CollectedAt DESC` 이력 조회 인덱스
3. 논리 식별키와 `PayloadHash` 중복 판정 인덱스
4. 논리 식별키에서 `IsLatest=1`만 허용하는 필터형 UNIQUE 인덱스

최신 상태만 조회할 때는 반드시 `WHERE IsLatest = 1`을 사용한다. 상태 변화 추적은 동일 논리 식별키를 `CollectedAt`, `StagingId` 순으로 조회한다.

## 6. 데이터 보안 및 운영 주의사항

- 고객명, 전화번호, 주소, 배송메모, 개인통관정보 등 개인정보는 정형 컬럼으로 저장하지 않는다.
- `RawJson`은 저장 전에 개인정보 키를 `***`로 마스킹한다.
- 인증키와 토큰은 어떤 테이블에도 저장하지 않는다.
- `RawJson`은 채널별 장애 분석용이며 일반 조회는 정형 컬럼을 우선 사용한다.
- `CollectionRunId`는 주문 이력과 감사 실행을 추적하기 위한 값이다. 주문 테이블에는 물리 FK를 두지 않아 채널별 적재 트랜잭션을 독립적으로 유지한다.
- 수량 컬럼에는 0 이상 CHECK 제약이 있으며 `RawJson`에는 JSON 유효성 CHECK 제약이 있다.

## 7. DDL 적용·검증 순서

1. `001_database_prerequisites.sql`
2. `005_verify_object_contract.sql`
3. `010_create_naver_godomall_tables.sql`
4. `020_create_coupang_lotteon_tables.sql`
5. `030_create_elevenst_ssg_tables.sql`
6. `040_create_toss_shopping_table.sql`
7. `045_create_cj_onstyle_table.sql`
8. `047_create_kakao_shopping_table.sql`
9. `050_create_channel_order_indexes.sql`
10. `060_verify_history_constraints.sql`
11. `070_extend_channel_order_api_fields.sql`
12. `075_verify_extended_channel_columns.sql`
13. `080_create_collection_audit_tables.sql`
14. `085_verify_collection_audit_tables.sql`
15. `090_verify_channel_order_tables.sql`

`099_drop_channel_order_tables.sql`은 전체 주문 테이블 삭제용이므로 신규 구축·일반 배포 과정에서 실행하지 않는다.
