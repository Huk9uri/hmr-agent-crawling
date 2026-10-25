# HMR Order Collection

8개 쇼핑몰의 주문·배송 데이터를 API로 수집하여 SQL Server에 저장하는 Python 프로젝트입니다. 채널별 주문상품의 변경 이력을 관리하며, 수동 수집 CLI와 Windows 작업 스케줄러 기반 정기 수집을 제공합니다.

## 주요 기능

- 채널별 인증, 조회 기간 분할, 페이지네이션 및 주문상품 필드 정규화
- 주문상품 데이터의 해시를 비교하여 신규·변경 데이터를 저장하고 동일 데이터는 건너뛰기
- 변경 시 이력 행을 추가하고 `IsLatest = 1`로 최신 상태 구분
- 채널별 트랜잭션과 SQL Server 애플리케이션 잠금으로 중복 실행 제어
- 정기 실행 시 기본 4개 채널 병렬 처리, 실패 시 10분 간격으로 최대 2회 추가 재시도
- 실행·시도 이력 DB 기록 및 상태·건수 중심의 JSON 출력

## 지원 채널

아래 기간은 현재 코드의 요청 분할 및 최대 기간 수집에 사용하는 일수입니다. 시작일과 종료일을 모두 포함하며, API에서 조회할 수 있는 과거 데이터의 보존 기간을 의미하지는 않습니다.

| 채널 | CLI 이름 | 요청당 조회 기간 |
| --- | --- | ---: |
| 네이버 스마트스토어 | `naver` | 1일 |
| 쿠팡 | `coupang` | 31일 |
| 고도몰 | `godomall` | 31일 |
| 롯데ON | `lotteon` | 1일 |
| 11번가 | `elevenst` | 31일 |
| SSG.COM | `ssg` | 180일 |
| CJ온스타일 | `cj_onstyle` | 31일 |
| 토스쇼핑 | `toss` | 31일 |

기준: [`channels/__init__.py`](src/hmr_order_collection/channels/__init__.py)의 `MAXIMUM_WINDOW_DAYS`.

## 설치 및 설정

Python 3.12를 사용합니다. DB 저장에는 SQL Server와 접속 계정이 필요하며, 채널에 따라 수집 서버의 IP 등록이 필요합니다. 아래 명령은 저장소 루트의 PowerShell에서 실행합니다.

```powershell
py -3.12 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements.lock
Copy-Item .env.example .env
$env:PYTHONPATH = Join-Path (Get-Location).Path 'src'
```

`.env`에 실제 인증 정보를 입력합니다. `requirements.lock`은 해시가 포함된 전체 의존성 목록이고, `requirements.txt`는 직접 의존성 목록입니다.

| 용도 | 설정 키 |
| --- | --- |
| 네이버 | `NAVER_COMMERCE_CLIENT_ID`, `NAVER_COMMERCE_CLIENT_SECRET` |
| 쿠팡 | `COUPANG_VENDOR_ID`, `COUPANG_ACCESS_KEY`, `COUPANG_SECRET_KEY` |
| 고도몰 | `GODOMALL_PARTNER_KEY`, `GODOMALL_USER_KEY` |
| 롯데ON | `LOTTEON_API_KEY` |
| 11번가 | `ELEVENST_API_KEY` |
| SSG.COM | `SSG_API_KEY` |
| CJ온스타일 | `CJ_ONSTYLE_VENDOR_CODE`, `CJ_ONSTYLE_AUTHENTICATION_KEY` |
| 토스쇼핑 | `TOSS_SHOPPING_ACCESS_KEY`, `TOSS_SHOPPING_SECRET_KEY` |
| SQL Server | `DB_SERVER`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_PORT` |
| 정기 수집 동시 실행 수 | `ORCHESTRATOR_MAX_WORKERS` |

`DB_NAME` 예시는 `ecommerce`, `DB_PORT` 기본값은 `1433`입니다. `ORCHESTRATOR_MAX_WORKERS` 기본값은 `4`이며 `1`부터 등록 채널 수인 `8`까지 설정할 수 있습니다.

설정은 기본적으로 `.env`에서 읽으며 `--config`로 다른 파일을 지정할 수 있습니다. 운영체제 환경변수를 자동으로 병합하지 않습니다. DB 설정은 CLI의 `--write-db` 및 정기 수집 실행에 필요합니다.

## 수동 수집

### 지원 채널 확인

```powershell
& .\.venv\Scripts\python.exe -m hmr_order_collection.cli list
```

### 단일 채널 조회

```powershell
& .\.venv\Scripts\python.exe -m hmr_order_collection.cli collect `
  --channel naver --from 2026-10-24 --to 2026-10-24 --dry-run
```

날짜는 `YYYY-MM-DD` 형식입니다. 지정 기간이 채널의 요청당 조회 기간보다 길면 자동으로 분할합니다.

`--dry-run`은 실제 API를 호출하여 수집 결과를 확인하고 DB에는 저장하지 않습니다. 모드를 생략해도 dry-run으로 실행됩니다. DB 저장은 스키마 준비 후 `--dry-run`을 `--write-db`로 바꾸어 실행합니다.

### 전체 채널 최대 기간 조회

```powershell
& .\.venv\Scripts\python.exe -m hmr_order_collection.cli collect-all `
  --to 2026-10-24 --maximum-window --dry-run --continue-on-error
```

각 채널은 `--to`를 종료일로 위 표의 조회 기간만큼 수집합니다. `collect-all`은 순차 실행하며, `--continue-on-error`를 지정하면 일부 채널이 실패해도 다음 채널을 시도합니다. 기간 경계 확인용 `--probe-boundaries`는 dry-run에서만 사용할 수 있습니다.

### 네이버·롯데ON 과거 데이터 보충

```powershell
& .\.venv\Scripts\python.exe -m hmr_order_collection.cli backfill `
  --channel naver --cutoff 2026-10-25 --days 30 --dry-run
```

`backfill`은 `naver`, `lotteon`만 지원하며 `--days`는 1~30, 기본 30입니다. 위 예시는 기준일을 제외한 2026-09-25부터 2026-10-24까지를 하루씩 조회하고 주문상품 식별자로 중복을 제거합니다. 검증 후 `--write-db`로 저장합니다. 수동 보충 작업의 완료 여부는 별도로 기록하며 정기 작업에는 추가하지 않습니다.

### 출력과 종료 코드

CLI는 채널별 `status`, `windows`, `pages`, `records`, `inserted`, `changed`, `skipped` 등을 JSON으로 출력합니다.

| 종료 코드 | 의미 |
| --- | --- |
| `0` | 모든 대상 채널 성공 |
| `1` | 일부 또는 전체 채널 실패 |
| `2` | 인자·설정·DB 연결 등 초기화 실패 |

## 데이터베이스 준비

기존 SQL Server 데이터베이스의 `dbo` 스키마를 사용합니다. SSMS에서 대상 DB를 선택하고 아래 순서대로 실행합니다.

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
sql/channel_orders/070_extend_channel_order_api_fields.sql
sql/channel_orders/075_verify_extended_channel_columns.sql
sql/channel_orders/080_create_collection_audit_tables.sql
sql/channel_orders/085_verify_collection_audit_tables.sql
```

`090_verify_channel_order_tables.sql`은 SQLCMD 모드에서 프로젝트 루트를 기준으로 실행하는 통합 검증 스크립트입니다. `099_drop_channel_order_tables.sql`은 테이블 삭제용이므로 초기 설치 순서에 포함하지 않습니다.

채널별 주문상품 테이블 8개와 감사 테이블 `CHANNEL_COLLECTION_RUN`, `CHANNEL_COLLECTION_ATTEMPT`를 사용합니다. 테이블 구조와 이력 제약은 [테이블 운영 가이드](docs/channel-order-tables.md)를 참고하세요.

## 정기 수집

오케스트레이터는 **API 수집과 DB 저장을 함께 수행**합니다. 채널마다 실행일을 종료일로 최대 조회 기간을 다시 조회하고, 변경되지 않은 데이터는 건너뜁니다.

```powershell
& .\.venv\Scripts\python.exe -m hmr_order_collection.orchestrator --config .env
```

`--date YYYY-MM-DD`로 실행 기준일을 지정할 수 있습니다. 기본값은 서버의 현재 날짜입니다. 서버 시간대를 한국 표준시로 설정하여 운영합니다. 재시도 횟수와 대기 시간은 `--retry-attempts`와 `--retry-delay-seconds`로 조정할 수 있습니다.

전체 실행 잠금과 채널별 잠금을 사용하며, 재시도 대기 중에는 작업 스레드를 점유하지 않습니다. 채널 실패는 해당 채널의 DB 트랜잭션에만 영향을 줍니다. 종료 코드는 `0` 성공, `1` 채널 실패, `2` 초기화 실패 또는 실행 중복입니다.

Windows 정기 작업을 등록하기 전에 경로를 검증합니다.

```powershell
$projectRoot = (Get-Location).Path
& .\scripts\windows\install_daily_order_collection_task.ps1 `
  -ProjectRoot $projectRoot `
  -PythonExe (Join-Path $projectRoot '.venv\Scripts\python.exe') `
  -ConfigPath (Join-Path $projectRoot '.env') `
  -ValidateOnly
```

검증 후 관리자 PowerShell에서 `-ValidateOnly`를 제외하고 실행하면 매일 시각 **14:00**, `SYSTEM` 계정으로 작업을 등록합니다. 기본 로그 경로는 `C:\ProgramData\HMR_Order_Collection\logs`입니다. `SYSTEM`의 파일 접근 권한과 DB 접속을 확인해야 합니다.

감사 이력 조회, 실패 상태 해석, 작업 해제 방법은 [정기 수집 운영 가이드](docs/daily-order-collection-operations.md)를 참고하세요. 

## 개발 및 테스트

저장소 루트에서 의존성을 설치하고 `PYTHONPATH`를 설정한 뒤 실행합니다.

```powershell
$env:PYTHONPATH = Join-Path (Get-Location).Path 'src'
& .\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

테스트는 API 응답 fixture와 모의 연결을 사용하여 어댑터, CLI, 이력 저장, 마스킹, 병렬 실행 및 SQL·스케줄러 스크립트 계약을 검증합니다. 실제 API 인증 및 운영 DB 연동 확인은 별도로 수행합니다.

## 프로젝트 구조

```text
src/hmr_order_collection/
  channels/          # 채널별 API 어댑터
  cli.py             # 수동 수집·보충 CLI
  orchestrator.py    # 병렬 정기 수집·재시도
  database.py        # 주문상품 이력 저장
  audit.py           # 실행 감사·애플리케이션 잠금
  config.py          # 설정 파일 로딩
  http.py            # 공통 HTTP 처리
  models.py          # 수집 데이터 모델
  masking.py         # 민감 정보 마스킹
  field_dictionary.py # 채널 필드 사전
sql/channel_orders/  # 스키마 생성·확장·검증 SQL
scripts/windows/     # 정기 실행·작업 스케줄러 등록
tests/               # 단위 테스트 및 응답 fixture
docs/                # 운영 가이드·설계·배포 기록
```

## 관련 문서

- [채널 API 필드 사전](docs/channel-api-field-dictionary.md)
- [채널별 주문상품 테이블 운영 가이드](docs/channel-order-tables.md)
- [정기 수집 운영 가이드](docs/daily-order-collection-operations.md)
- [주문 수집 현황](docs/SALES_TEAM_ORDER_COLLECTION_STATUS.md)
- [네이버·롯데ON 수동 보충 가이드](docs/2026-09-02-naver-lotteon-manual-backfill.md)

기존 설계·배포 문서는 작성 시점의 내용을 포함합니다. 현재 조회 기간과 옵션은 소스 코드 및 CLI `--help`를 기준으로 확인합니다.
