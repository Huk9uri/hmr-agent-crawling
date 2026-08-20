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

## Collector CLI

Use Python 3.12 and install the fully resolved, hash-locked runtime from
`requirements.lock`. `requirements.txt` contains only the direct dependency
inputs used to regenerate that lock.
Configuration is loaded strictly from `.env` (or the file passed with
`--config`). Use `.env.example` as the key-only template; API and database
credentials are never accepted as command-line arguments.

```powershell
python -m pip install --require-hashes -r requirements.lock
$env:PYTHONPATH = "src"
python -m hmr_order_collection.cli list
python -m hmr_order_collection.cli collect --channel naver --from 2026-08-10 --to 2026-08-10 --dry-run
python -m hmr_order_collection.cli collect-all --to 2026-08-10 --maximum-window --dry-run --continue-on-error
python -m hmr_order_collection.cli collect-all --to 2026-08-10 --maximum-window --probe-boundaries --dry-run --continue-on-error
python -m hmr_order_collection.cli collect-all --to 2026-08-10 --maximum-window --verified-maximum-days godomall=28 --verified-maximum-days elevenst=7 --write-db --continue-on-error
```

Regenerate the lock only as an intentional dependency update:

```powershell
uv pip compile requirements.txt --python-version 3.12 --generate-hashes --output-file requirements.lock
```

Collection is a dry run by default. Database persistence is enabled only by
the explicit `--write-db` flag. The CLI emits one JSON summary containing
channel names, status, window/page/record/write counts, and safe probe counts;
it never emits order records, exception
messages, response bodies, PII, API credentials, or database credentials.
Use `--continue-on-error` to attempt later channels after a channel failure.
The process still exits nonzero when any channel fails.

The initial maximum-window policy always ends on the explicit `--to` date:

| Channel | Inclusive days | Current basis |
|---|---:|---|
| Naver SmartStore | 1 | changed-order endpoint limit |
| Coupang | 31 | order-sheet endpoint limit |
| Godomall | 1 | conservative pre-live boundary |
| LotteON | 1 | adapter/API search limit |
| 11st | 1 | conservative pre-live boundary |
| SSG.COM | 180 | shipping-direction endpoint limit |
| Toss Shopping | 31 | order endpoint limit |

Godomall and 11st remain at a conservative one-day range until the controller
performs the planned authenticated, read-only boundary checks after independent
code review. Do not widen either range based only on HTTP status.

`--probe-boundaries` is dry-run-only. It starts Godomall at 31 inclusive days,
11st at 7, and LotteON at its official 1-day limit. A candidate is reduced by
one day only when the adapter recognizes an explicit invalid-period business
response; authentication, transport, parsing, and other business failures stop
that channel without reduction. The JSON summary exposes `probe_attempts`,
`probe_invalid_periods`, `verified_maximum_days`, and `pages` as count-only
metadata. LotteON is never queried above one day.

After reviewing a successful probe summary, pass each approved Godomall or 11st
value to the later maximum-window command with repeatable
`--verified-maximum-days channel=days` options. The write summary includes
`applied_verified_maximum_days` for that channel. Godomall values must be 1-31
and 11st values 1-7. LotteON is fixed at one day and cannot be overridden;
unknown channels, duplicate entries, malformed integers, and out-of-range
values fail before configuration is loaded. Never copy an unreviewed value from
an unsuccessful or partial probe.

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

이 스크립트는 위 7개 테이블만 삭제하며 `dbo` 스키마나 다른 `ecommerce` 객체는 변경하지 않는다.

## 현재 배포 상태

2026-08-10 `ecommerce` 데이터베이스에 7개 채널별 주문상품 테이블과 28개 인덱스를 적용했다. 객체·컬럼·인덱스 검증과 7개 가상 행 INSERT 후 ROLLBACK 검증을 완료했으며, 검증용 데이터는 남지 않았다.
