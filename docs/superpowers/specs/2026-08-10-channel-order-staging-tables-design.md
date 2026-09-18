# 채널별 주문상품 원본 테이블 설계

- 작성일: 2026-08-10
- 대상 DBMS: Microsoft SQL Server (SSMS)
- 범위: 실제 주문조회가 검증된 판매채널의 원본 주문상품 저장 테이블

## 1. 목적

판매채널마다 서로 다른 주문 API 응답을 손실 없이 저장하면서, 후속 단계에서 공통 주문·상품·배송 모델과 대시보드 VIEW로 변환할 수 있는 채널별 원본 저장 영역을 구축한다. 논리적 역할은 스테이징이지만 기존 `ecommerce` 데이터베이스 관례에 맞춰 별도 `stg` 스키마를 만들지 않고 `dbo` 스키마를 사용한다.

이번 구현은 채널별 테이블까지만 포함한다. 공통 `core` 테이블, 수집 실행 이력 테이블, 원본 응답 전용 테이블 및 대시보드 VIEW는 후속 구현 범위다.

## 2. 대상 테이블

실제 운영 API 호출이 검증된 다음 7개 채널을 구현한다.

1. `dbo.NAVER_SMARTSTORE_ORDER_ITEM`
2. `dbo.GODOMALL_ORDER_ITEM`
3. `dbo.COUPANG_ORDER_ITEM`
4. `dbo.LOTTEON_ORDER_ITEM`
5. `dbo.ELEVENST_ORDER_ITEM`
6. `dbo.SSG_ORDER_ITEM`
7. `dbo.TOSS_SHOPPING_ORDER_ITEM`

테이블명은 모두 영문 대문자 스네이크 케이스로 작성한다. `ELEVENST`는 숫자로 시작하는 객체명과 대괄호 의존을 피하기 위한 11번가 영문 식별자다.

CJ온스타일, 지마켓·옥션 ESM 및 알리익스프레스는 인증 승인이 완료되고 실제 응답을 확인한 뒤 별도 테이블로 추가한다.

## 3. 행 단위와 상태 이력

- 각 행은 주문상품 한 건을 나타낸다.
- 동일 주문에 상품이 여러 개면 상품별로 행을 분리한다.
- 동일 주문상품의 상태가 변경되면 기존 행을 덮어쓰지 않고 새 이력 행을 추가한다.
- 동일 주문상품에서 가장 최근에 수집된 행만 `IsLatest = 1`로 유지한다.
- 수집기는 새 행 추가와 기존 최신 행 해제를 하나의 트랜잭션으로 처리한다.

채널별 논리 주문상품 식별자는 다음과 같다.

| 채널 | 논리 식별자 |
|---|---|
| 네이버 스마트스토어 | `ProductOrderId` |
| 고도몰 | `OrderNo + OrderItemSno` |
| 쿠팡 | `ShipmentBoxId + OrderItemId` |
| 롯데ON | `OrderNo + OrderItemSeq` |
| 11번가 | `OrderNo + OrderProductNo` |
| SSG.COM | `OrdNo + OrdItemSeq + ShppNo + ShppSeq` |
| 토스쇼핑 | `OrderProductId` |

## 4. 공통 관리 컬럼

모든 채널 테이블은 다음 관리 컬럼을 공통으로 가진다.

| 컬럼 | SQL Server 형식 | 설명 |
|---|---|---|
| `StagingId` | `bigint IDENTITY(1,1)` | 물리 기본키 |
| `CollectionRunId` | `uniqueidentifier` | 한 번의 수집 실행을 식별하는 값 |
| `CollectedAt` | `datetime2(3)` | API 응답 수집 시각(UTC) |
| `SourceCreatedAt` | `datetime2(3) NULL` | 채널 원본 주문 생성 시각 |
| `SourceModifiedAt` | `datetime2(3) NULL` | 채널 원본 최종 변경 시각 |
| `RawOrderStatus` | `nvarchar(100) NULL` | 채널 원본 주문상태 |
| `RawDeliveryStatus` | `nvarchar(100) NULL` | 채널 원본 배송상태 |
| `RawJson` | `nvarchar(max)` | 해당 주문상품의 개인정보 마스킹 JSON |
| `PayloadHash` | `binary(32)` | 마스킹 JSON의 SHA-256 해시 |
| `IsLatest` | `bit` | 논리 주문상품의 최신 행 여부 |
| `CreatedAt` | `datetime2(3)` | DB 행 생성시각(UTC) |

`RawJson`에는 고객명, 전화번호, 주소, 이메일, 개인통관번호 등 개인정보 원문을 저장하지 않는다. SQL 제약조건 `ISJSON(RawJson) = 1`을 적용한다.

## 5. 채널별 업무 컬럼

각 테이블은 실제 API 응답에서 확인한 주문·상품·수량·금액·배송 필드를 명시 컬럼으로 가진다. 채널에 존재하지 않는 의미를 억지로 공통 컬럼에 맞추지 않으며, 원본 필드 의미와 단위를 유지한다.

### 네이버 스마트스토어

주문·상품주문 ID, 상품·옵션 ID와 이름, 수량, 결제금액, 상품주문·클레임·배송상태, 결제·발송·배송완료 시각, 택배사와 송장번호를 저장한다.

### 고도몰

주문번호와 상품 순번, `orderChannelFl`, 상품·옵션·수량, 판매·결제·할인·배송비, 주문·결제·배송상태, 외부 주문번호, 택배사와 송장번호를 저장한다. 일반몰·네이버페이·페이코는 `OrderChannelCode`로 구분한다.

### 쿠팡 WING

Shipment Box·Order·Order Item 식별자, 벤더 상품·옵션 ID, 수량·취소수량, 판매가격, 주문·결제·예정배송·출고·배송완료 시각, 주문·배송상태, 택배사와 송장번호를 저장한다.

### 롯데ON

주문번호와 주문상품 순번, 상품·옵션 식별자, 주문·취소수량, 판매·결제금액, 주문·배송상태, 주문·결제·출고·배송 시각, 택배사와 송장번호를 저장한다.

### 11번가

주문번호와 주문상품번호, 상품·옵션 식별자, 수량, 주문금액, 주문·배송상태, 주문·결제·발송 시각, 택배사와 송장번호를 저장한다. 실제 주문이 0건이었던 검증 상태를 고려해 문서상 필드와 최초 실주문 응답 차이는 이후 확장 컬럼으로 반영한다.

### SSG.COM

주문·주문상품·배송 식별자, 사이트번호, 상품·단품·협력업체 상품 ID, 상품명, 주문·지시·취소수량, 공급가·판매가·결제가·할인가, 주문·배송·상세배송상태, 주문접수·완료·출고예정 시각을 저장한다.

### 토스쇼핑

`orderId`, `orderProductId`, 상품·재고 ID, 상품·옵션명, 수량, 판매가·정상가·할인·포인트, 주문상품 상태, 주문·취소·구매확정 시각, 택배사·송장번호, 배송비 및 상품 관리코드를 저장한다.

## 6. 키와 인덱스

- 모든 테이블은 `StagingId`를 클러스터형 기본키로 사용한다.
- `CollectionRunId`에 비클러스터형 인덱스를 생성한다.
- 채널별 논리 식별자와 `CollectedAt DESC` 복합 인덱스를 생성한다.
- `IsLatest = 1` 필터 인덱스를 채널별 논리 식별자에 생성하여 최신 행 조회와 중복 검사를 지원한다.
- `PayloadHash`를 논리 식별자와 함께 인덱싱해 동일 상태 응답의 불필요한 중복 이력 적재를 방지한다.

## 7. 데이터 형식 원칙

- 외부 식별자는 숫자로 보여도 `nvarchar`로 저장해 선행 0과 규격 변경을 보존한다. 토스쇼핑처럼 API가 명시적으로 `int64`를 보장하는 식별자만 `bigint`를 사용한다.
- 금액은 원화 정수 응답이면 `bigint`, 소수 또는 외화 가능성이 있으면 `decimal(19,4)`를 사용한다.
- 수량은 `int`를 사용한다.
- 모든 시스템 시각은 UTC `datetime2(3)`로 저장한다.
- 채널 응답에 시간대 정보가 없으면 수집기에서 채널 문서의 시간대를 적용한 뒤 UTC로 변환한다.
- 원본 상태 코드는 번역하지 않고 그대로 저장한다.

## 8. 오류 및 보안 처리

- 필수 논리 식별자가 없는 응답은 테이블에 적재하지 않고 수집 오류로 기록한다.
- `RawJson`이 유효한 JSON이 아니면 제약조건으로 적재를 거부한다.
- 개인정보는 수집기에서 마스킹한 뒤 DB에 전달한다.
- API 키, Secret Key, Access Token은 어떤 테이블에도 저장하지 않는다.
- 상태 변경 API는 호출하지 않으며 모든 수집은 조회 전용 API를 사용한다.

## 9. 검증 기준

- SQL 스크립트를 빈 SQL Server 데이터베이스에서 실행했을 때 7개 테이블과 모든 인덱스가 생성된다.
- 같은 논리 주문상품에 여러 상태 이력을 삽입할 수 있다.
- 같은 논리 주문상품에 `IsLatest = 1` 행이 둘 이상 존재하지 않는다.
- 잘못된 JSON은 삽입되지 않는다.
- 각 채널의 마스킹 샘플 응답을 주문상품 1행으로 삽입할 수 있다.
- 롤백 스크립트로 이번 구현에서 만든 객체만 제거할 수 있다.

## 10. 구현 산출물

- `sql/staging/001_database_prerequisites.sql`
- `sql/staging/010_create_channel_order_item_tables.sql`
- `sql/staging/020_create_channel_order_item_indexes.sql`
- `sql/staging/090_verify_channel_order_item_tables.sql`
- `sql/staging/099_drop_channel_order_item_tables.sql`
- `docs/channel-order-staging-schema.md`

현재 프로젝트는 Git 저장소가 아니므로 설계 문서 커밋은 수행하지 않는다.
