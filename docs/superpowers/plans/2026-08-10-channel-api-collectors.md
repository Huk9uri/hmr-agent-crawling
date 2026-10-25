# 채널 API 수집기 구현 계획

> **에이전트 작업자 안내:** 필수 하위 스킬로 superpowers:subagent-driven-development(권장) 또는 superpowers:executing-plans를 사용하여 이 계획을 작업별로 구현합니다. 진행 상황은 체크박스(`- [ ]`)로 추적합니다.

**목표:** 인증된 7개 판매 채널의 읽기 전용 API 수집기를 만들고, 배포된 SQL Server 채널 테이블에 주문상품당 한 행을 안전하게 추가합니다.

**구조:** 공통 Python 패키지가 설정, 재시도, 마스킹, 페이로드 해시, 수집 실행 메타데이터, SQL Server 이력 저장을 담당합니다. 각 채널 어댑터는 인증, 최대 허용 조회 기간, 페이지네이션, 응답 추출 및 해당 채널 테이블 매핑만 담당합니다. CLI는 채널별 dry-run과 명시적 DB 저장 모드를 제공하여 삽입 전에 API 응답을 검증할 수 있게 합니다.

**기술 스택:** Python 3.12, `requests`, `pymssql`, 표준 라이브러리 `unittest`, SQL Server 2017, `.env`의 환경 설정 값.

## 공통 제약 사항

- 읽기 전용 주문 API만 호출합니다. 주문 확인, 발송 처리, 취소, 반품, 교환 및 채널 상태 변경을 수행하지 않습니다.
- API 키, 액세스 토큰, 수취인명, 전화번호, 주소, 이메일, 통관 식별자를 출력하거나 저장하지 않습니다.
- JSON 직렬화와 해시 계산 전에 민감 필드를 재귀적으로 마스킹합니다.
- 채널 실행마다 하나의 `CollectionRunId`를 사용하고 `CollectedAt`은 UTC로 기록합니다.
- 문서화된 다음 페이지 토큰이 없어질 때까지 모든 페이지를 조회합니다.
- 요청 기간은 각 API의 최대 허용 구간으로 분할하며 임의로 잘라내지 않습니다.
- 주문상품당 한 행을 저장하고 이력을 유지합니다. 최신 `PayloadHash`가 같으면 삽입을 건너뜁니다.
- 변경 시 하나의 DB 트랜잭션에서 기존 최신 행을 `IsLatest = 0`으로 바꾸고 새 행을 `IsLatest = 1`로 삽입합니다.
- 채널 실패로 다른 채널의 커밋된 데이터를 롤백하지 않습니다. 해당 채널을 실패로 기록하고 `--continue-on-error`를 지정한 경우에만 계속합니다.
- `.env`, 응답 본문 원문, 토큰 캐시는 Git 제외 상태를 유지합니다.

## 파일 구조

```text
src/hmr_order_collection/
  __init__.py              패키지 표시 파일
  cli.py                   목록 조회·dry-run·수집 명령
  config.py                비밀정보를 로그에 남기지 않는 엄격한 .env 로딩
  http.py                  제한 시간·재시도·호출 속도 제한·JSON/XML 보조 기능
  masking.py               재귀적 개인정보 마스킹 및 정규 JSON
  models.py                ChannelRecord·CollectionResult 계약
  database.py              pymssql 연결 및 이력 저장
  channels/
    __init__.py            어댑터 레지스트리
    base.py                ChannelAdapter 인터페이스 및 조회 구간 반복자
    naver.py               OAuth2, 24시간 변경 주문 페이지 조회, ID 300개씩 상세 조회
    coupang.py              HMAC 서명, 상태별 반복, 31일 구간, nextToken
    godomall.py             파트너·사용자 키, Order_Search, lastOrder 페이지 조회
    lotteon.py              API 키, 배송 주문·진행 조회
    elevenst.py             openapikey를 통한 XML 주문 조회
    ssg.py                  Authorization 키, 180일 배송 지시 조회
    toss.py                 OAuth2 토큰, 31일 구간, nextCursor 페이지 조회
tests/
  test_masking.py
  test_windows.py
  test_database.py
  test_naver.py
  test_coupang.py
  test_godomall.py
  test_lotteon.py
  test_elevenst.py
  test_ssg.py
  test_toss.py
  fixtures/                마스킹된 가상 API 응답만 포함
```

---

### 작업 1: 공통 계약, 설정, 마스킹 및 HTTP 동작

**파일:**
- 생성: `src/hmr_order_collection/config.py`
- 생성: `src/hmr_order_collection/models.py`
- 생성: `src/hmr_order_collection/masking.py`
- 생성: `src/hmr_order_collection/http.py`
- 테스트: `tests/test_masking.py`

**인터페이스:**
- `load_config(path: Path) -> AppConfig`
- `mask_payload(value: object) -> object`
- `canonical_payload(value: object) -> tuple[str, bytes]`
- `ChannelRecord(identity: tuple, columns: dict, raw_json: str, payload_hash: bytes)`

- [ ] 이름·전화번호·주소·이메일·통관·인증 정보에 해당하는 name, phone, tel, address, email, customs, token, secret, key 중첩 키가 `***`로 치환되고 주문·상품 식별자는 유지되는지 테스트합니다.
- [ ] `python -m unittest tests.test_masking -v`를 실행하여 패키지가 없어 실패하는지 확인합니다.
- [ ] 엄격한 `.env` 파싱, 불변 데이터클래스 모델, 재귀 마스킹, 정렬된 안정적 JSON, SHA-256 해시, 연결/읽기 제한 시간 10/60초, 429·5xx에 대한 제한된 재시도, 오류 시 본문을 로그에 남기지 않는 응답 파싱을 구현합니다.
- [ ] 마스킹 테스트가 통과하는지 확인합니다.
- [ ] `feat: add collector foundations`로 커밋합니다.

### 작업 2: 조회 기간 분할 및 SQL Server 이력 저장기

**파일:**
- 생성: `src/hmr_order_collection/channels/base.py`
- 생성: `src/hmr_order_collection/database.py`
- 테스트: `tests/test_windows.py`
- 테스트: `tests/test_database.py`

**인터페이스:**
- `iter_windows(start: date, end: date, maximum_days: int) -> Iterator[DateWindow]`
- `ChannelAdapter.fetch(window: DateWindow) -> Iterator[ChannelRecord]`
- `DatabaseWriter.write(channel: str, records: Iterable[ChannelRecord], run_id: UUID) -> WriteSummary`

- [ ] 시작일·종료일을 포함하는 1·24·31·180일 구간 경계와 동일·변경·신규 페이로드 판정에 대한 실패 테스트를 작성합니다.
- [ ] 날짜가 겹치지 않고 양 끝을 포함하는 구간 생성과 배포된 7개 테이블의 허용 목록 기반 테이블/식별자 매핑을 구현합니다.
- [ ] 매개변수화된 `pymssql` 문을 구현합니다. 현재 최신 식별자 행을 잠그고 `PayloadHash`를 비교한 뒤 하나의 트랜잭션에서 `IsLatest` 갱신과 새 행 삽입을 수행합니다.
- [ ] 행 하나라도 실패하면 롤백되며 API 데이터에서 SQL 식별자를 가져오지 않는지 검증합니다.
- [ ] `feat: add collection history writer`로 커밋합니다.

### 작업 3: 네이버 스마트스토어·쿠팡 어댑터

**파일:**
- 생성: `src/hmr_order_collection/channels/naver.py`
- 생성: `src/hmr_order_collection/channels/coupang.py`
- 테스트: `tests/test_naver.py`
- 테스트: `tests/test_coupang.py`

**인터페이스:**
- 네이버는 OAuth2 클라이언트 자격 증명, 24시간 변경 주문 구간, `more.moreFrom`과 `more.moreSequence`, 최대 300개 상품주문 ID의 상세 조회 묶음을 사용합니다.
- 쿠팡은 HMAC-SHA256 서명, 6개 전체 주문 상태, 양 끝을 포함한 최대 31일 구간, `maxPerPage=50`을 사용하며 `nextToken`이 없어질 때까지 조회합니다.

- [ ] 토큰 발급, 후속 페이지, 상세 조회 묶음, 전체 상태 수집 및 `NAVER_SMARTSTORE_ORDER_ITEM`·`COUPANG_ORDER_ITEM` 매핑에 대한 마스킹된 가상 fixture와 실패 테스트를 추가합니다.
- [ ] 읽기 전용 요청과 정확한 채널 매핑을 구현합니다.
- [ ] 다음 페이지 토큰을 추적하여 반복 페이지로 무한 루프가 생기지 않는지 검증합니다.
- [ ] `feat: add Naver and Coupang collectors`로 커밋합니다.

### 작업 4: 고도몰·롯데ON·11번가 어댑터

**파일:**
- 생성: `src/hmr_order_collection/channels/godomall.py`
- 생성: `src/hmr_order_collection/channels/lotteon.py`
- 생성: `src/hmr_order_collection/channels/elevenst.py`
- 테스트: `tests/test_godomall.py`
- 테스트: `tests/test_lotteon.py`
- 테스트: `tests/test_elevenst.py`

**인터페이스:**
- 고도몰은 `Order_Search.php`를 호출하고 `lastOrder`를 따라 조회하며 일반·네이버페이·페이코 주문을 구분하도록 `orderChannelFl`을 유지합니다.
- 롯데ON은 `SellerDeliveryOrdersSearch`와 `SellerDeliveryProgressStateSearch`를 모두 호출하고 주문·상품 식별자로 응답을 결합하며 상태 변경 API를 호출하지 않습니다.
- 11번가는 `openapikey`로 읽기 전용 주문 엔드포인트를 호출하고 XML을 방어적으로 파싱하며 `orderProductNo` 하나를 한 행에 매핑합니다.

- [ ] 페이지네이션, 빈 결과, XML 네임스페이스, 롯데ON 배송 정보 결합 및 채널별 필드 매핑의 실패 fixture 테스트를 작성합니다.
- [ ] 검증된 엔드포인트와 인증 헤더로 각 어댑터를 구현합니다.
- [ ] 성공한 빈 응답은 오류가 아닌 0건으로 처리합니다.
- [ ] `feat: add Godomall LotteON and 11st collectors`로 커밋합니다.

### 작업 5: SSG.COM·토스쇼핑 어댑터

**파일:**
- 생성: `src/hmr_order_collection/channels/ssg.py`
- 생성: `src/hmr_order_collection/channels/toss.py`
- 테스트: `tests/test_ssg.py`
- 테스트: `tests/test_toss.py`

**인터페이스:**
- SSG는 `perdType=02`로 `/api/pd/1/listShppDirection.ssg`를 최대 180일 구간으로 호출하고 각 `(ordNo, ordItemSeq, shppNo, shppSeq)`를 행에 매핑합니다.
- 토스는 OAuth2 클라이언트 자격 증명 토큰을 발급받아 `limit=50`으로 최대 31일 구간을 조회하고 `success.nextCursor`가 null일 때까지 계속합니다.

- [ ] SSG 결과 코드, 토스 `resultType`, 토큰 갱신, 후속 페이지, 개인정보 마스킹 및 정확한 테이블 매핑의 실패 테스트를 작성합니다.
- [ ] 두 읽기 전용 어댑터를 구현하고 토스가 HTTP 200을 반환해도 업무 오류는 실패로 처리합니다.
- [ ] `feat: add SSG and Toss collectors`로 커밋합니다.

### 작업 6: CLI, dry-run, 최대 기간 보충 수집 및 운영 검증

**파일:**
- 생성: `src/hmr_order_collection/cli.py`
- 생성: `src/hmr_order_collection/channels/__init__.py`
- 생성: `tests/test_cli.py`
- 수정: `.gitignore`
- 수정: `docs/channel-order-tables.md`

**인터페이스:**
- `python -m hmr_order_collection.cli list`
- `python -m hmr_order_collection.cli collect --channel naver --from YYYY-MM-DD --to YYYY-MM-DD --dry-run`
- `python -m hmr_order_collection.cli collect-all --to 2026-08-10 --maximum-window --write-db`

- [ ] DB 저장에 `--write-db`가 필요하고 미래 날짜·알 수 없는 채널이 거부되며 요약에는 비밀정보와 개인정보 없이 건수만 포함되는지 실패 테스트를 작성합니다.
- [ ] 어댑터 레지스트리, 채널별 실행, JSON 요약 출력 및 종료 코드를 구현합니다.
- [ ] 전체 `unittest`와 `git diff --check`를 실행합니다.
- [ ] 인증된 모든 채널에 먼저 dry-run을 수행하고 채널별 구간·페이지·레코드 수와 마스킹된 실패 정보를 기록합니다.
- [ ] dry-run 성공 채널에만 DB 저장을 수행하고 삽입·건너뛰기·변경 건수와 최신 행 단일성 조건을 확인합니다.
- [ ] SQL Server에서 채널별 행 수를 조회하고 `RawJson` 표본에 마스킹되지 않은 개인정보 키가 없는지 확인합니다.
- [ ] `feat: collect channel orders into SQL Server`로 커밋합니다.

## 초기 과거 데이터 수집 기간

첫 운영 실행은 2026-08-10을 종료일로 각 엔드포인트에서 당시 검증된 최대 단일 요청 기간을 사용합니다. CLI는 계속해서 기간을 분할하고 모든 응답을 페이지 단위로 조회합니다.

| 채널 | 초기 조회 기간 정책 |
|---|---|
| 네이버 스마트스토어 | 24시간 단위 변경 주문 조회, `moreFrom`·`moreSequence`로 후속 조회 |
| 쿠팡 | 전체 주문 상태별 이전 31일, `nextToken` 페이지네이션 |
| 고도몰 | dry-run 경계 탐색으로 허용되는 최대 `Order_Search` 기간 확인, `lastOrder` 페이지네이션 |
| 롯데ON | dry-run 경계 탐색으로 허용되는 최대 배송 주문 기간 확인, 주문·진행 API 조회 |
| 11번가 | dry-run 경계 탐색으로 허용되는 최대 주문 기간 확인, 주문 확인·발송 API 호출 금지 |
| SSG.COM | 주문 완료일 기준 이전 180일 |
| 토스쇼핑 | 이전 31일, 전체 상태, `limit=50`, `nextCursor` 페이지네이션 |

경계 탐색은 문서화되었거나 이전에 검증한 범위에서 시작하고 API가 명시적인 조회 기간 오류를 반환할 때만 범위를 줄입니다. 채널 상태를 변경하지 않으며 HTTP 상태만으로 성공을 판단하지 않습니다.

## 계획 자체 검토

- 배포된 7개 테이블 모두에 어댑터 작업과 정확한 DB 저장 대상이 지정되어 있습니다.
- 공통 마스킹은 JSON 해시 계산과 저장 전에 수행합니다.
- 모든 페이지네이션 방식에 종료 조건과 토큰 반복 방지가 있습니다.
- 인증과 접근이 실제 승인되기 전까지 CJ온스타일·G마켓/옥션·알리익스프레스는 읽기 전용 수집 범위에서도 제외합니다.
- 응답 fixture에는 실제 주문·고객 데이터가 없습니다.
- 미구현 자리표시자 단계가 없습니다.
