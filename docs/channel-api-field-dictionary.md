# 채널별 주문·배송 API 필드 사전

정확한 필드 단위 계약은 [`tests/fixtures/channel_field_contracts.json`](../tests/fixtures/channel_field_contracts.json)에 있으며, `field_dictionary.render_field_dictionary()`가 채널 순서대로 동일한 Markdown 표를 생성한다.

| 채널 | 적재 테이블 | 주문·배송 API 범위 | 비고 |
|---|---|---|---|
| 네이버 스마트스토어 | `NAVER_SMARTSTORE_ORDER_ITEM` | 변경 주문 + 상품주문 상세 | 주문·결제·발주·배송 필드 확장 |
| 토스쇼핑 | `TOSS_SHOPPING_ORDER_ITEM` | 주문상품 목록 | 공식 비민감 응답 필드 기존 반영 완료 |
| 한촌몰·고도몰 | `GODOMALL_ORDER_ITEM` | `Order_Search.php` | 네이버페이 주문 포함, `OrderChannelCode`로 구분 |
| 쿠팡 WING | `COUPANG_ORDER_ITEM` | 6개 발주상태 주문목록 | 배송박스·주문상품 필드 결합 |
| 롯데ON | `LOTTEON_ORDER_ITEM` | 배송주문 + 배송진행 | `OrderNo + OrderItemSeq` 결합 |
| SSG.COM | `SSG_ORDER_ITEM` | 출고지시 + 출고완료 + 미배송완료 + 배송완료 | 네 단계 응답을 배송 식별자로 결합 |
| 11번가 | `ELEVENST_ORDER_ITEM` | 검증된 `complete`, `shipping` XML | 미검증 오류 엔드포인트는 제외 |

## 관리 원칙

- 채널이 제공하는 비민감 주문·배송 업무 필드는 채널별 명시 컬럼과 마스킹된 `RawJson`에 함께 저장한다.
- 개인정보는 정형 평문 컬럼에 추가하지 않으며 `RawJson`에서도 마스킹한다.
- 인증키·Secret·Token·세션은 저장하지 않는다.
- 새 응답 필드를 발견하면 필드 계약에 `stored`, `masked`, `structural`, `transport` 중 하나로 분류한 뒤 SQL과 수집기를 변경한다.
- 확장 DDL은 `070_extend_channel_order_api_fields.sql`, 계약 검증은 `075_verify_extended_channel_columns.sql`을 사용한다.
