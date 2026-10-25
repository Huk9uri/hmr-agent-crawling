# 채널별 주문상품 테이블 운영 가이드

## 대상 데이터베이스

- SQL Server 데이터베이스: `ecommerce`
- 스키마: 기존 `dbo`
- 별도 `stg` 스키마는 사용하지 않는다.

## 생성 대상

1. `dbo.NAVER_SMARTSTORE_ORDER_ITEM`
2. `dbo.GODOMALL_ORDER_ITEM`
3. `dbo.COUPANG_ORDER_ITEM`
4. `dbo.LOTTEON_ORDER_ITEM`
5. `dbo.ELEVENST_ORDER_ITEM`
6. `dbo.SSG_ORDER_ITEM`
7. `dbo.TOSS_SHOPPING_ORDER_ITEM`
8. `dbo.CJ_ONSTYLE_ORDER_ITEM`

각 행은 주문상품 한 건의 한 시점 상태다. 동일 주문상품의 상태가 바뀌면 기존 행을 수정하지 않고 새 행을 추가한다. 최신 행은 `IsLatest = 1`이며 필터형 UNIQUE 인덱스가 주문상품별 최신 행을 하나로 제한한다.

## SSMS 실행 순서

SSMS에서 `ecommerce` 데이터베이스를 명시적으로 선택하고 다음 파일을 순서대로 실행한다.

```text
sql/channel_orders/001_database_prerequisites.sql
sql/channel_orders/010_create_naver_godomall_tables.sql
sql/channel_orders/020_create_coupang_lotteon_tables.sql
sql/channel_orders/030_create_elevenst_ssg_tables.sql
sql/channel_orders/040_create_toss_shopping_table.sql
sql/channel_orders/045_create_cj_onstyle_table.sql
sql/channel_orders/050_create_channel_order_indexes.sql
sql/channel_orders/005_verify_object_contract.sql
sql/channel_orders/060_verify_history_constraints.sql
```

통합 검증은 SQLCMD 모드를 활성화한 뒤 프로젝트 루트에서 다음 파일을 실행한다.

```text
sql/channel_orders/090_verify_channel_order_tables.sql
```

## 수집기 CLI

Python 3.12를 사용하고, 전체 의존성과 해시가 고정된 `requirements.lock`으로 실행 환경을 설치합니다. `requirements.txt`에는 잠금 파일을 다시 생성하는 데 사용하는 직접 의존성만 포함되어 있습니다.
설정은 `.env` 또는 `--config`로 지정한 파일에서만 읽습니다. `.env.example`을 설정 키 템플릿으로 사용하며, API 및 DB 인증 정보는 명령행 인자로 받지 않습니다.

```powershell
python -m pip install --require-hashes -r requirements.lock
$env:PYTHONPATH = "src"
python -m hmr_order_collection.cli list
python -m hmr_order_collection.cli collect --channel naver --from 2026-08-10 --to 2026-08-10 --dry-run
python -m hmr_order_collection.cli collect-all --to 2026-08-10 --maximum-window --dry-run --continue-on-error
python -m hmr_order_collection.cli collect-all --to 2026-08-10 --maximum-window --probe-boundaries --dry-run --continue-on-error
python -m hmr_order_collection.cli collect-all --to 2026-08-10 --maximum-window --verified-maximum-days godomall=28 --verified-maximum-days elevenst=7 --write-db --continue-on-error
```

의존성을 명시적으로 갱신할 때만 잠금 파일을 다시 생성합니다:

```powershell
uv pip compile requirements.txt --python-version 3.12 --generate-hashes --output-file requirements.lock
```

수집은 기본적으로 dry-run으로 실행하며, `--write-db`를 명시한 경우에만 DB에 저장합니다. CLI는 채널명, 상태, 조회 구간·페이지·레코드·저장 건수, 안전한 경계 탐색 건수만 포함한 JSON 요약을 출력합니다. 주문 레코드, 예외 메시지, 응답 본문, 개인정보, API 및 DB 인증 정보는 출력하지 않습니다.
`--continue-on-error`를 지정하면 채널 실패 후에도 다음 채널을 시도합니다. 하나라도 실패하면 프로세스는 0이 아닌 종료 코드를 반환합니다.

저장 모드는 정기 오케스트레이터와 동일한 SQL Server 애플리케이션 잠금 `HMR_ORDER_COLLECTION:{channel}`을 사용합니다. 잠금은 API 수집부터 해당 채널의 저장 트랜잭션까지 유지하고 즉시 해제합니다.
자동 오케스트레이터는 채널별로 독립 연결과 트랜잭션을 사용하고, `ORCHESTRATOR_MAX_WORKERS=4`를 기준으로 최대 4개 시도를 동시에 실행합니다. 재시도 대기 중에는 작업 스레드나 채널 잠금을 유지하지 않습니다. 비상 시 값을 `1`로 설정하여 순차 실행으로 전환할 수 있습니다.

초기 최대 조회 기간의 종료일은 항상 명시한 `--to` 날짜입니다:

| 채널 | 시작일·종료일 포함 일수 | 당시 적용 근거 |
|---|---:|---|
| 네이버 스마트스토어 | 1 | 변경 주문 엔드포인트 제한 |
| 쿠팡 | 31 | 발주서 엔드포인트 제한 |
| 고도몰 | 1 | 실연동 전 보수적으로 설정한 경계 |
| 롯데ON | 1 | 어댑터/API 검색 제한 |
| 11번가 | 1 | 실연동 전 보수적으로 설정한 경계 |
| SSG.COM | 180 | 배송 지시 엔드포인트 제한 |
| 토스쇼핑 | 31 | 주문 엔드포인트 제한 |

고도몰과 11번가는 독립 코드 검토 후 제어 담당자가 인증된 읽기 전용 경계 검증을 수행하기 전까지 보수적인 1일 범위를 유지합니다. HTTP 상태만 보고 조회 범위를 넓히지 않습니다.

`--probe-boundaries`는 dry-run에서만 사용할 수 있습니다. 고도몰은 시작일·종료일을 포함한 31일, 11번가는 7일, 롯데ON은 공식 제한인 1일부터 시작합니다. 어댑터가 명시적인 조회 기간 오류 업무 응답을 인식한 경우에만 후보 기간을 하루 줄입니다. 인증, 통신, 파싱 및 다른 업무 오류는 기간을 줄이지 않고 해당 채널 실행을 중단합니다. JSON 요약은 `probe_attempts`, `probe_invalid_periods`, `verified_maximum_days`, `pages`를 건수 메타데이터로 제공합니다. 롯데ON은 1일을 초과하여 조회하지 않습니다.

성공한 경계 탐색 요약을 검토한 후, 승인된 고도몰 또는 11번가 값을 반복 가능한 `--verified-maximum-days channel=days` 옵션으로 후속 최대 기간 수집 명령에 전달합니다. 저장 요약에는 채널별 `applied_verified_maximum_days`가 포함됩니다. 고도몰은 1~31, 11번가는 1~7이어야 합니다. 롯데ON은 1일로 고정되어 재정의할 수 없습니다. 알 수 없는 채널, 중복 항목, 잘못된 정수 및 범위 밖 값은 설정 파일을 읽기 전에 실패합니다. 실패하거나 일부만 성공한 탐색에서 검토되지 않은 값을 복사하지 않습니다.

생성 스크립트와 인덱스 스크립트는 두 번 실행해도 같은 객체를 중복 생성하지 않는다.

## 적재 트랜잭션

상태가 변경된 주문상품을 적재할 때는 다음 두 작업을 하나의 트랜잭션에서 수행한다.

1. 기존 최신 행의 `IsLatest`를 `0`으로 변경한다.
2. 새로운 상태 행을 `IsLatest = 1`로 삽입한다.

`PayloadHash`가 기존 최신 행과 같으면 상태와 마스킹 JSON이 동일하므로 새 이력 행 삽입을 생략할 수 있다.

필터형 최신행 인덱스가 있으므로 수집기 DB 연결에서도 `ANSI_NULLS`, `ANSI_PADDING`, `ANSI_WARNINGS`, `ARITHABORT`, `CONCAT_NULL_YIELDS_NULL`, `QUOTED_IDENTIFIER`를 `ON`으로, `NUMERIC_ROUNDABORT`를 `OFF`로 유지해야 한다. 제공된 인덱스 및 통합 검증 SQL은 이 옵션을 직접 설정한다.

## 개인정보와 인증정보

- `RawJson`에는 고객명, 전화번호, 주소, 이메일, 개인통관번호를 마스킹한 값만 저장한다.
- API Key, Secret Key, Access Token 및 Refresh Token은 DB에 저장하지 않는다.
- DB와 애플리케이션 로그에 개인정보 원문을 출력하지 않는다.

## 시간 기준

- DB 생성 시각은 `SYSUTCDATETIME()`으로 저장한다.
- API 원본 시각은 수집기에서 UTC로 변환한 뒤 `datetime2(3)`에 저장한다.
- 원본 상태 코드는 번역하지 않고 그대로 저장한다.

## 롤백

`099_drop_channel_order_tables.sql`은 기본값에서 실행을 거부한다. 삭제가 승인된 비운영 검증 DB에서만 파일 상단의 `CONFIRM_DROP` 값을 `YES`로 변경해 실행한다.

이 스크립트는 위 8개 테이블만 삭제하며 `dbo` 스키마나 다른 `ecommerce` 객체는 변경하지 않는다.

## 현재 배포 상태

2026-08-10 `ecommerce` 데이터베이스에 7개 채널별 주문상품 테이블과 28개 인덱스를 적용했다. 객체·컬럼·인덱스 검증과 7개 가상 행 INSERT 후 ROLLBACK 검증을 완료했으며, 검증용 데이터는 남지 않았다.
