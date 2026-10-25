# SSG 빈 배송 단계 표시값 처리 설계

## 문제

SSG 배송 지시 API는 주문 1건을 반환하지만 출고 API는 빈 결과를 `warehouseOuts: [""]`로 나타냅니다. 공통 단계 파서는 모든 목록 요소를 객체로 간주하여 `ValueError`를 발생시키고 유효한 배송 지시 주문의 DB 저장을 막습니다.

## 설계

SSG 후속 단계 목록의 빈 문자열을 빈 결과 표시값으로 정규화합니다. `null`, 빈 문자열, 단일 객체, 객체 목록에 대한 기존 처리를 유지합니다. 실제 응답 계약 변경을 놓치지 않도록 비어 있지 않은 문자열과 다른 잘못된 요소는 계속 거부합니다.

4개 API 수집 흐름은 유지합니다. 배송 지시를 먼저 수집하고 출고·미배송·배송 완료 데이터가 있으면 결합합니다. 빈 후속 단계는 필드를 추가하지 않지만 기본 주문을 버리지 않습니다.

## 검증 및 운영

출고 응답으로 `[""]`를 제공해도 배송 지시 레코드가 반환되는지 회귀 테스트를 추가합니다. SSG 대상 테스트 후 전체 테스트를 실행합니다. 마지막으로 2026-08-12를 종료일로 검증된 180일 구간을 DB 저장 모드로 수집하고 테이블 행 수, 최신 행 수, 수집 시각을 확인합니다.

## 승인된 필드 출처 수정

기존 `listWarehouseOut` 엔드포인트는 출고 처리 대상 목록이므로 배포된 출고 완료 컬럼의 유효한 출처가 아닙니다. 정보 보강 흐름에서 제거합니다. 배송 지시 응답의 배송번호마다 `commType: "02"`, `commValue: <ShppNo>` 빠른 검색 매개변수로 `listNonDelivery`와 `listDeliveryEnd`를 조회합니다.

테이블 스키마 변경 없이 공식 SSG 필드를 매핑합니다:

- `whoutDt` → `WarehouseOutCompletedAt`
- `delicoVenId` → `DeliveryCompanyCode`
- `wblNo` → `TrackingNumber`
- `shppDt` → `DeliveryCompletedAt`
- `lastShppProgStatDtlCd` → `ShippingProgressDetailCode`, `RawDeliveryStatus`

승인된 API에 대응 시각이 문서화되어 있지 않으므로 `DeliveryTrackingStatusAt`은 null로 유지합니다. 두 빠른 검색 응답의 빈 문자열 목록 요소는 빈 결과 표시값입니다. 비어 있지 않은 잘못된 요소와 업무 실패는 계속 오류로 처리합니다.

다른 채널 어댑터나 테이블 스키마는 변경하지 않습니다.
