# 채널별 주문·배송 테이블 컬럼 사전

이 문서는 `ecommerce.dbo`에 적재되는 채널별 주문상품 테이블의 컬럼 의미를 설명한다. 한 행은 주문 전체가 아니라 **주문상품 1건의 한 시점 상태**를 나타낸다. 같은 주문상품의 상태나 응답 내용이 변경되면 새 이력 행이 추가되고 최신 행만 `IsLatest = 1`이 된다.

## 공통 관리 컬럼

아래 컬럼은 일곱 개 채널 테이블에 공통으로 존재한다.

| 컬럼 | 의미 |
|---|---|
| `StagingId` | 테이블 내부에서 사용하는 자동 증가 행 식별자. 채널 주문번호와는 무관하다. |
| `CollectionRunId` | 한 번의 수집 실행을 식별하는 UUID. 같은 실행에서 적재된 행을 묶는 데 사용한다. |
| `CollectedAt` | 수집기가 API 응답을 받아 DB에 적재한 시각(UTC). |
| `SourceCreatedAt` | 채널 응답에서 확인한 원본 데이터 생성 시각. 현재 직접 매핑되지 않는 채널은 `NULL`이다. |
| `SourceModifiedAt` | 채널 응답에서 확인한 원본 최종 변경 시각. 현재 직접 매핑되지 않는 채널은 `NULL`이다. |
| `RawOrderStatus` | 변환하지 않은 채널 원본 주문 상태 코드. |
| `RawDeliveryStatus` | 변환하지 않은 채널 원본 배송 상태 코드 또는 배송진행 상세 코드. |
| `RawJson` | 해당 주문상품의 API 원본을 JSON으로 보존한 값. 개인정보는 `***`로 마스킹된다. |
| `PayloadHash` | 마스킹된 `RawJson`의 SHA-256 해시. 이전 최신 행과 응답이 같은지 판정한다. |
| `IsLatest` | 동일 주문상품 이력 중 최신 행이면 `1`, 과거 행이면 `0`. |
| `CreatedAt` | SQL Server에서 행이 생성된 시각(UTC). |

---

## `NAVER_SMARTSTORE_ORDER_ITEM`

논리키는 `ProductOrderId`이다. 네이버 변경 주문 조회 후 상품주문 상세 응답의 `order`, `productOrder`, `delivery` 객체를 한 행으로 저장한다.

| 컬럼 | 의미 | 주요 원본 필드 |
|---|---|---|
| `ProductOrderId` | 네이버 상품주문 단위 ID. 테이블의 논리키. | `productOrder.productOrderId` |
| `OrderId` | 여러 상품주문을 묶는 네이버 주문 ID. | `order.orderId` |
| `ProductId` | 네이버 상품 ID. | `productOrder.productId` |
| `OptionId` | 상품주문에 연결된 옵션/아이템 번호. | `productOrder.itemNo` |
| `OptionManageCode` | 판매자가 지정한 옵션 관리 코드. | `productOrder.optionManageCode` |
| `ProductName` | 주문 당시 상품명. | `productOrder.productName` |
| `OptionName` | 주문 당시 선택 옵션명. | `productOrder.productOption` |
| `Quantity` | 주문 수량. | `productOrder.quantity` |
| `UnitPrice` | 상품 1개 기준 판매 단가. | `productOrder.unitPrice` |
| `TotalPaymentAmount` | 해당 상품주문의 최종 결제금액. | `productOrder.totalPaymentAmount` |
| `OrderDiscountAmount` | 주문 단위 할인금액. | `order.orderDiscountAmount` |
| `GeneralPaymentAmount` | 포인트 등을 제외한 일반 결제수단 결제금액. | `order.generalPaymentAmount` |
| `DeliveryFeeAmount` | 상품주문에 부과된 배송비. | `productOrder.deliveryFeeAmount` |
| `SectionDeliveryFee` | 묶음배송 구간에 적용된 배송비. | `productOrder.sectionDeliveryFee` |
| `ProductOrderStatus` | 상품주문의 현재 상태. 예: 결제완료, 배송중, 배송완료. | `productOrder.productOrderStatus` |
| `ClaimStatus` | 취소·반품·교환 등 클레임 상태. | `productOrder.claimStatus` |
| `DeliveryStatus` | 네이버 배송 상태. | `delivery.deliveryStatus` |
| `OrderDate` | 주문 생성 시각. | `order.orderDate` |
| `PaymentAt` | 결제 완료 시각. | `order.paymentDate` |
| `PaymentMeans` | 카드, 계좌 등 결제수단 코드. | `order.paymentMeans` |
| `PayLocationType` | PC·모바일 등 결제 위치 유형. | `order.payLocationType` |
| `ShippingDueDate` | 판매자가 발송해야 하는 기한. | `productOrder.shippingDueDate` |
| `PlaceOrderDate` | 판매자가 발주확인한 시각. | `productOrder.placeOrderDate` |
| `PlaceOrderStatus` | 발주확인 상태. | `productOrder.placeOrderStatus` |
| `ExpectedDeliveryMethod` | 주문 시 예상된 배송방법. | `productOrder.expectedDeliveryMethod` |
| `DeliveryAttributeType` | 일반배송 등 배송 속성 유형. | `productOrder.deliveryAttributeType` |
| `DeliveryMethod` | 실제 배송방법. | `delivery.deliveryMethod` |
| `DispatchAt` | 판매자가 상품을 발송한 시각. | `delivery.sendDate` |
| `DeliveryCompletedAt` | 배송완료 시각. | `delivery.deliveredDate` |
| `DeliveryCompanyCode` | 택배사 코드. | `delivery.deliveryCompany` |
| `TrackingNumber` | 운송장 번호. | `delivery.trackingNumber` |

---

## `GODOMALL_ORDER_ITEM`

논리키는 `OrderNo + OrderItemSno`이다. 한촌몰 일반 주문과 네이버페이 주문을 모두 고도몰 `Order_Search.php`에서 수집한다. `OrderChannelCode`로 유입 채널을 구분한다.

| 컬럼 | 의미 | 주요 원본 필드 |
|---|---|---|
| `OrderNo` | 고도몰 주문번호. | `orderNo` |
| `OrderItemSno` | 고도몰 주문상품 일련번호. | `orderGoodsData.sno` |
| `OrderChannelCode` | 주문 유입 채널 코드. 네이버페이 주문은 통상 `naverpay`. | `orderChannelFl` |
| `ExternalOrderNo` | 네이버페이 등 외부 채널의 주문번호. | `apiOrderNo` |
| `OrderTypeCode` | 고도몰 주문 유형 코드. | `orderTypeFl` |
| `SettlementMethodCode` | 결제·정산수단 코드. | `settleKind` |
| `ProductCode` | 고도몰 상품번호 또는 판매자 상품코드. | `goodsNo`, `goodsCd` |
| `OptionCode` | 고도몰 옵션 일련번호. | `optionSno` |
| `ProductName` | 주문 당시 상품명. | `goodsNm` |
| `OptionName` | 선택 옵션 또는 텍스트 옵션 정보. | `optionInfo`, `optionTextInfo` |
| `Quantity` | 주문상품 수량. | `goodsCnt` |
| `UnitPrice` | 상품 기본 판매단가. | `goodsPrice` |
| `OptionPrice` | 옵션 추가금액. | `optionPrice` |
| `AdditionalGoodsPrice` | 추가상품 금액. | `addGoodsPrice` |
| `GoodsDiscountAmount` | 상품 자체 할인금액. | `goodsDcPrice` |
| `CouponGoodsDiscountAmount` | 상품쿠폰 할인금액. | `couponGoodsDcPrice` |
| `PaymentAmount` | 주문의 최종 결제금액. 주문의 모든 상품행에 반복 저장된다. | `settlePrice` |
| `TotalGoodsPrice` | 주문 전체 상품금액 합계. | `totalGoodsPrice` |
| `OrderDiscountAmount` | 주문 단위 할인금액. | `totalOrderDcPrice` |
| `MemberDiscountAmount` | 회원등급 등 회원 할인금액. | `totalMemberDcPrice` |
| `CouponOrderDiscountAmount` | 주문쿠폰 할인금액. | `totalCouponOrderDcPrice` |
| `UsedMileageAmount` | 결제에 사용한 마일리지. | `totalMileage` |
| `UsedDepositAmount` | 결제에 사용한 예치금. | `totalDeposit` |
| `DiscountAmount` | 기존 호환용 상품할인 합계 컬럼. | `totalGoodsDcPrice` |
| `DeliveryFee` | 주문 배송비 합계. | `totalDeliveryCharge` |
| `OrderStatus` | 주문상품 기준 현재 고도몰 상태. | 상품 또는 주문의 `orderStatus` |
| `PaymentStatus` | 결제 흐름 판정에 사용하는 고도몰 주문 상태. | 주문의 `orderStatus` |
| `DeliveryStatus` | 배송 흐름 판정에 사용하는 고도몰 주문상품 상태. | 상품 또는 주문의 `orderStatus` |
| `OrderedAt` | 주문 접수 시각. | `orderDate` |
| `PaidAt` | 결제 완료 시각. 상품 값이 있으면 상품 값을 우선한다. | `paymentDt` |
| `DispatchedAt` | 상품 발송/배송처리 시각. | `deliveryDt` |
| `DeliveryCompanyCode` | 고도몰 택배사 일련번호. | `invoiceCompanySno` |
| `TrackingNumber` | 운송장 번호. | `invoiceNo` |

---

## `COUPANG_ORDER_ITEM`

논리키는 `ShipmentBoxId + OrderItemId`이다. 쿠팡 발주서의 배송박스 정보와 그 안의 주문상품을 결합한다.

| 컬럼 | 의미 | 주요 원본 필드 |
|---|---|---|
| `ShipmentBoxId` | 쿠팡 배송박스 ID. | `shipmentBoxId` |
| `OrderId` | 쿠팡 주문 ID. | `orderId` |
| `OrderItemId` | 배송박스 안 주문상품 순번. 선행 0을 보존한다. | `orderItems.sequenceNo` |
| `VendorItemId` | 쿠팡 판매옵션 단위 ID. | `orderItems.vendorItemId` |
| `SellerProductId` | 판매자가 등록한 상품 ID. | `orderItems.sellerProductId` |
| `SellerProductItemId` | 판매자가 등록한 상품옵션 ID. | `orderItems.sellerProductItemId` |
| `ProductId` | 쿠팡 상품 ID. | `orderItems.productId` |
| `VendorItemPackageId` | 묶음·패키지 상품 ID. | `orderItems.vendorItemPackageId` |
| `VendorItemPackageName` | 패키지 상품명. | `orderItems.vendorItemPackageName` |
| `VendorItemName` | 쿠팡 벤더아이템 표시명. | `orderItems.vendorItemName` |
| `ProductName` | 판매자 상품명. | `orderItems.sellerProductName` |
| `OptionName` | 판매자 상품옵션명. | `orderItems.sellerProductItemName` |
| `Quantity` | 출고 대상 수량. | `orderItems.shippingCount` |
| `CanceledQuantity` | 취소된 수량. | `orderItems.cancelCount` |
| `HeldCancellationQuantity` | 취소 요청으로 보류 중인 수량. | `orderItems.holdCountForCancel` |
| `SalesPrice` | 주문상품 판매금액. `units + nanos`로 계산한다. | `orderItems.salesPrice` |
| `SalesPriceCurrencyCode` | 판매금액 통화코드. | `orderItems.salesPrice.currencyCode` |
| `OrderStatus` | 발주서 상태. | `status` |
| `DeliveryStatus` | 현재 구현에서 발주서 상태를 배송 상태로 함께 저장한 값. | `status` |
| `OrderedAt` | 주문 생성 시각. | `orderedAt` |
| `PaidAt` | 결제 완료 시각. | `paidAt` |
| `EstimatedShippingAt` | 출고 예정일. | `orderItems.estimatedShippingDate` |
| `DispatchedAt` | 배송 시작 시각. 원본 필드명의 오탈자를 그대로 사용한다. | `inTrasitDateTime` |
| `DeliveryCompletedAt` | 배송완료 시각. | `deliveredDate` |
| `DeliveryCompanyCode` | 택배사명 또는 코드. | `deliveryCompanyName` |
| `TrackingNumber` | 운송장 번호. | `invoiceNumber` |

---

## `LOTTEON_ORDER_ITEM`

논리키는 `OrderNo + OrderItemSeq`이다. 배송주문 조회와 배송진행상태 조회를 결합한다.

| 컬럼 | 의미 | 주요 원본 필드 |
|---|---|---|
| `OrderNo` | 롯데ON 주문번호. | `odNo` |
| `OrderItemSeq` | 주문상품 순번. | `odSeq` |
| `ProcessSequence` | 배송 또는 주문 처리 순번. 배송진행 응답을 우선한다. | `procSeq` |
| `ProductId` | 판매상품 또는 상품 ID. | `spdNo`, `pdNo` |
| `OptionId` | 단품·옵션 ID. | `sitmNo`, `itmNo` |
| `ProductName` | 주문상품명. | `spdNm`, `pdNm` |
| `OptionName` | 단품·옵션명. | `sitmNm`, `itmNm` |
| `Quantity` | 주문 수량. | `odQty` |
| `CanceledQuantity` | 취소 수량. | `cnclQty` |
| `SalesAmount` | 판매금액. | `slAmt` |
| `PaymentAmount` | 실 결제금액. | `actualAmt` |
| `OrderStatus` | 주문 진행단계 코드. | 배송주문의 `odPrgsStepCd` |
| `DeliveryStatus` | 배송 진행단계 코드. 진행상태 응답을 우선한다. | `odPrgsStepCd` |
| `OrderedAt` | 주문 완료/접수 시각. | `odCmptDttm` |
| `PaidAt` | 결제 완료 시각. | `payDttm` |
| `DispatchedAt` | 출고 완료 시각. | `owhoDttm` |
| `DeliveryCompletedAt` | 배송완료 상태의 배송추적 발생 시각. | `dvTrcStatDttm` |
| `DeliveryCompanyCode` | 배송업체 코드. | `dvCoCd` |
| `TrackingNumber` | 운송장 번호. | `invcNo` |

---

## `ELEVENST_ORDER_ITEM`

논리키는 `OrderNo + OrderProductNo`이다. 검증된 `complete`, `shipping` XML 응답을 합치며 같은 상품이 양쪽에 있으면 `shipping` 응답을 우선한다.

| 컬럼 | 의미 | 주요 원본 필드 |
|---|---|---|
| `OrderNo` | 11번가 주문번호. | `orderNo` |
| `OrderProductNo` | 11번가 주문상품번호. | `orderProductNo` |
| `ProductId` | 11번가 상품번호 또는 판매자 상품번호. | `productNo`, `sellerProductNo` |
| `OptionId` | 옵션번호. | `optionNo`, `productOptionNo` |
| `ProductName` | 주문상품명. | `productName` |
| `OptionName` | 선택 옵션명. | `optionName`, `productOption` |
| `Quantity` | 주문 수량. | `quantity`, `orderQuantity`, `buyQuantity` |
| `OrderAmount` | 주문 또는 결제금액. | `orderAmount`, `payAmount`, `salePrice` |
| `OrderStatus` | 주문 상태. | `orderStatus`, `orderStatusType` |
| `DeliveryStatus` | 배송 상태. | `deliveryStatus`, `deliveryStatusType` |
| `OrderedAt` | 주문 생성 시각. | `orderDate`, `orderedAt` |
| `PaidAt` | 결제 완료 시각. | `paymentDate`, `paidAt` |
| `DispatchedAt` | 발송/배송 시작 시각. | `dispatchDate`, `deliveryStartDate` |
| `DeliveryCompanyCode` | 택배사 코드 또는 명칭. | `deliveryCompanyCode`, `deliveryCompany` |
| `TrackingNumber` | 운송장 번호. | `invoiceNo`, `trackingNumber` |

---

## `SSG_ORDER_ITEM`

논리키는 `OrdNo + OrdItemSeq + ShppNo + ShppSeq`이다. 출고지시, 출고완료, 미배송완료, 배송완료 API를 동일한 배송 식별자로 결합한다.

| 컬럼 | 의미 | 주요 원본 필드 |
|---|---|---|
| `OrdNo` | SSG 주문번호. | `ordNo` |
| `OrdItemSeq` | 주문상품 순번. | `ordItemSeq` |
| `ShppNo` | 배송번호. | `shppNo` |
| `ShppSeq` | 배송 순번. | `shppSeq` |
| `SiteNo` | 주문이 발생한 SSG 계열 사이트 번호. | `siteNo` |
| `ItemId` | 상품 ID. | `itemId` |
| `UitemId` | 단품/옵션 ID. | `uitemId` |
| `SplVenItemId` | 협력업체 상품 ID. | `splVenItemId` |
| `USplVenItemId` | 협력업체 단품/옵션 ID. | `uSplVenItemId` |
| `ItemName` | 상품명. | `itemNm` |
| `UnitItemName` | 단품·옵션명. | `uitemNm` |
| `OrderQuantity` | 최초 주문 수량. | `ordQty` |
| `DirectedQuantity` | 출고지시 수량. | `dircItemQty` |
| `CanceledQuantity` | 취소 수량. | `cnclItemQty` |
| `SupplyPrice` | 공급가. | `splprc` |
| `SalesPrice` | 판매가. | `sellprc` |
| `RealOrderAmount` | 할인 등을 반영한 실 주문금액. | `rlordAmt` |
| `DiscountAmount` | 할인금액. | `dcAmt` |
| `OrderStatusCode` | SSG 주문 상태 코드. | `ordStatCd` |
| `ShippingStatusCode` | 배송 상태 코드. | `shppStatCd` |
| `ShippingProgressDetailCode` | 배송진행 상세 상태 코드. | `shppProgStatDtlCd` |
| `OrderReceivedAt` | 주문 접수 시각. | `ordRcpDts` |
| `OrderCompletedAt` | 주문 완료 시각. | `ordCmplDts` |
| `ScheduledShippingDate` | 출고 예정일. | `shppRsvtDt` |
| `WarehouseOutCompletedAt` | 물류 출고 완료 시각. | `whoutCmplDts` |
| `DeliveryCompanyCode` | 택배사 코드. | `dvCoCd` |
| `TrackingNumber` | 운송장 번호. | `invcNo` |
| `DeliveryTrackingStatusAt` | 미배송완료/배송추적 상태가 확인된 시각. | `dvTrcStatDts` |
| `DeliveryCompletedAt` | 배송완료 시각. | `deliveryEndDts` |

---

## `TOSS_SHOPPING_ORDER_ITEM`

논리키는 `OrderProductId`이다. 토스쇼핑 주문상품 API의 비민감 업무 필드를 저장한다.

| 컬럼 | 의미 | 주요 원본 필드 |
|---|---|---|
| `OrderId` | 토스쇼핑 주문 ID. | `orderId` |
| `OrderProductId` | 토스쇼핑 주문상품 ID. 테이블의 논리키. | `orderProductId` |
| `ProductId` | 토스쇼핑 상품 ID. | `productId` |
| `StockId` | 상품 재고/옵션 ID. | `stockId` |
| `ProductName` | 주문 당시 상품명. | `productName` |
| `OptionName` | 주문 당시 옵션명. | `optionName` |
| `Quantity` | 주문 수량. | `quantity` |
| `Price` | 실제 판매가격. | `price` |
| `OriginPrice` | 할인 전 정상가격. | `originPrice` |
| `TotalDiscountPrice` | 전체 할인금액. | `totalDiscountPrice` |
| `TossShoppingDiscount` | 토스쇼핑 부담 할인금액. | `tossShoppingDiscount` |
| `TossPayDiscount` | 토스페이 할인금액. | `tossPayDiscount` |
| `TossPayPoint` | 결제에 사용하거나 적용된 토스페이 포인트. | `tossPayPoint` |
| `OrderProductStatus` | 주문상품 상태. 예: `PAID`, `PREPARING_PRODUCT`, `DELIVERING`, `DELIVERED`, `CONFIRMED_ORDER`. | `orderProductStatus` |
| `OrderedAt` | 주문 생성 시각. | `orderedAt` |
| `CanceledAt` | 결제취소/주문취소 시각. | `canceledAt` |
| `ConfirmedAt` | 구매확정 시각. | `confirmedAt` |
| `ShippingDeadlineAt` | 판매자가 발송해야 하는 기한. | `shippingDeadlineAt` |
| `DeliveryCompanyCode` | 택배사 코드. | `deliveryCompanyCode` |
| `ShippingTrackingNumber` | 운송장 번호. | `shippingTrackingNumber` |
| `DeliveryFeeGroupId` | 묶음 배송비 정책 그룹 ID. | `deliveryFeeGroupId` |
| `DeliveryFee` | 실제 부과 배송비. | `deliveryFee` |
| `DeliveryLocationType` | 일반·제주·도서산간 등 배송지역 유형. | `deliveryLocationType` |
| `NormalDeliveryFee` | 일반지역 기본 배송비. | `normalDeliveryFee` |
| `JejuDeliveryFee` | 제주지역 배송비. | `jejuDeliveryFee` |
| `MountainDeliveryFee` | 도서산간지역 배송비. | `mountainDeliveryFee` |
| `ProductManagementCode` | 판매자가 지정한 상품 관리코드. | `productManagementCode` |
| `ProductItemManagementCode` | 판매자가 지정한 상품옵션 관리코드. | `productItemManagementCode` |

## 사용 시 주의사항

- 주문 단위 금액이 주문상품 행마다 반복되는 채널이 있으므로 합계 계산 시 주문번호 중복을 확인해야 한다.
- `RawOrderStatus`와 `RawDeliveryStatus`는 채널별 코드 체계가 서로 다르므로 단순 문자열 비교로 채널 간 상태를 통합하면 안 된다.
- 현재값만 조회하려면 반드시 `IsLatest = 1` 조건을 사용한다.
- 상태 이력을 분석할 때는 논리키별 `CollectedAt` 순서로 조회한다.
- 고객명, 전화번호, 주소, 이메일 등 개인정보는 정형 컬럼으로 저장하지 않으며 `RawJson`에서도 마스킹된다.
# CJ온스타일

- 엔드포인트: `POST /delivery/getDeliveryList`
- 주문·배송 단계별 조회: 배송 지시(`dateType=2`, `deliveryStatus=2`), 출고(`3`,`4`), 배송 완료(`4`,`5`), 취소(`6`,`6`).
- 고정 식별자: `orderNo + orderItemSequence + orderDetailSequence + orderProcessingSequence`.
- 수취인, 전화번호, 주소, 배송 메모, 공동현관 비밀번호, 통관부호, 선물 및 자유 입력 클레임 필드는 정규 컬럼으로 저장하지 않고 `RawJson`에서 `***`로 마스킹합니다.
