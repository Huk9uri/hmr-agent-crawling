# SSG 빈 배송 단계 표시값 처리 구현 계획

> **에이전트 작업자 안내:** 필수 하위 스킬로 superpowers:subagent-driven-development(권장) 또는 superpowers:executing-plans를 사용하여 이 계획을 작업별로 구현합니다. 진행 상황은 체크박스(`- [ ]`)로 추적합니다.

**목표:** 유효한 SSG 배송 지시 주문을 유지하고 공식 필드명을 사용하는 배송번호 빠른 검색으로 정보를 보강한 뒤 복구된 주문을 SQL Server에 적재합니다.

**구조:** 배송 지시 응답으로 기본 행을 만들고 고유 배송번호마다 미배송·배송 완료 응답을 한 번씩 조회합니다. 빈 결과 표시값을 정규화하고 배포된 4개 요소 식별자로 공식 보강 필드를 결합하며 DB 저장 동작은 유지합니다.

**기술 스택:** Python 3.12, `unittest`, `requests`, `pymssql`을 통한 SQL Server 연결.

## 공통 제약 사항

- API 인증 정보, 응답 본문, 개인정보, 주문 원문 페이로드를 출력하지 않습니다.
- 다른 채널의 스키마나 어댑터를 변경하지 않습니다.
- 공백만 있는 문자열만 빈 결과 표시값으로 처리하며 비어 있지 않은 문자열은 계속 거부합니다.
- `listWarehouseOut`은 출고 완료 응답이 아닌 출고 처리 대상 목록이므로 호출하지 않습니다.
- 승인된 응답 필드에 근거가 없으므로 `DeliveryTrackingStatusAt`은 null로 둡니다.
- 운영 재적재에는 2026-08-12를 종료일로 시작일·종료일을 포함한 180일 SSG 조회 구간을 사용합니다.

---

### 작업 1: 후속 배송 단계의 빈 결과 표시값 허용

**파일:**
- 수정: `tests/test_ssg.py`
- 수정: `src/hmr_order_collection/channels/ssg.py`

**인터페이스:**
- 입력: `_stage_rows(value: Any, name: str) -> list[dict[str, Any]]`
- 산출물: 공백 문자열 표시값은 제외하고 딕셔너리는 유지한 단계별 행 목록.

- [ ] **단계 1: 실패하는 회귀 테스트 작성**

정상 `shppDirections` 응답, `{"resultCode": "00", "warehouseOuts": [""]}`, 나머지 단계의 성공한 빈 응답을 전달하는 테스트를 추가합니다. `list(adapter.fetch(...))`가 `ValueError`를 발생시키지 않고 기본 배송 지시 레코드를 반환하는지 검증합니다.

- [ ] **단계 2: 운영 결함으로 테스트가 실패하는지 확인**

실행: `python -m unittest tests.test_ssg.SsgAdapterTests.test_fetch_treats_blank_follow_up_stage_sentinel_as_empty -v`

예상 결과: `ValueError: SSG warehouseOuts list was malformed`로 실패합니다.

- [ ] **단계 3: 최소 정규화 구현**

나머지 요소가 모두 딕셔너리인지 검사하기 전에 `isinstance(row, str) and not row.strip()`을 만족하는 요소를 건너뛰도록 `_stage_rows`를 변경합니다.

- [ ] **단계 4: 대상 테스트 및 전체 테스트 검증**

실행: `python -m unittest tests.test_ssg -v`

예상 결과: 모든 SSG 테스트가 통과합니다.

실행: `python -m unittest discover -s tests -v`

예상 결과: 전체 프로젝트 테스트에서 실패와 오류가 없습니다.

- [ ] **단계 5: 회귀 수정 커밋**

```bash
git add -- tests/test_ssg.py src/hmr_order_collection/channels/ssg.py
git commit -m "fix: accept empty SSG follow-up stage sentinel"
```

### 작업 2: 배송번호 빠른 검색으로 정보 보강

**파일:**
- 수정: `tests/test_ssg.py`
- 수정: `src/hmr_order_collection/channels/ssg.py`

**인터페이스:**
- 입력: `(ordNo, ordItemSeq, shppNo, shppSeq)`를 키로 갖는 기본 레코드와 `listNonDelivery`·`listDeliveryEnd`의 빠른 검색 응답.
- 산출물: 공식 `whoutDt`, `delicoVenId`, `wblNo`, `shppDt`, `lastShppProgStatDtlCd` 필드를 사용하는 결합 레코드.

- [ ] **단계 1: 실패하는 빠른 검색·매핑 테스트 작성**

공식 응답 구조를 따르는 가상 데이터로 고유 `shppNo`마다 두 보강 엔드포인트에 `{"commType": "02", "commValue": shpp_no}`가 전달되고, `listWarehouseOut`은 호출되지 않으며, 공식 응답 필드가 배포된 컬럼에 저장되는지 검증합니다.

- [ ] **단계 2: 새 테스트 실패 확인**

지정한 SSG 빠른 검색·매핑 테스트를 `python -m unittest ... -v`로 실행합니다.

예상 결과: 기존 기간 조회, 폐기된 엔드포인트 호출, 공식 필드 매핑 누락으로 실패합니다.

- [ ] **단계 3: 빠른 검색 정보 보강 구현**

기본 행을 수집하고 고유 배송번호마다 빠른 검색 두 번을 수행합니다. 공식 `nonDeliverys`, `deliveryEnds` 키를 허용하고 일치하는 식별자를 결합한 뒤 승인된 필드를 매핑합니다. 비어 있지 않은 잘못된 값과 비성공 결과 코드의 실패 동작은 유지합니다.

- [ ] **단계 4: 대상 테스트 및 전체 테스트 실행**

실행: `python -m unittest tests.test_ssg -v`

실행: `python -m unittest discover -s tests -v`

예상 결과: 경고·오류·실패 없이 모든 테스트가 통과합니다.

- [ ] **단계 5: 정보 보강 수정 커밋**

```bash
git add -- tests/test_ssg.py src/hmr_order_collection/channels/ssg.py
git commit -m "fix: enrich SSG orders by shipping number"
```

### 작업 3: SSG 재적재 및 검증

**파일:**
- 소스 파일을 수정하지 않습니다.

**인터페이스:**
- 입력: `python -m hmr_order_collection.cli collect --channel ssg ... --write-db`
- 산출물: 건수 중심 수집 요약과 저장된 `dbo.SSG_ORDER_ITEM` 이력 행.

- [ ] **단계 1: 건수 확인용 dry-run 수행**

SSG 수집기를 `2026-02-14`부터 `2026-08-12`까지 `--dry-run`으로 실행합니다.

예상 결과: 상태 `ok`, 조회 페이지 4개, 레코드 1건 이상입니다.

- [ ] **단계 2: 검증된 동일 응답 저장**

같은 조회 구간을 `--write-db`로 실행합니다.

예상 결과: 상태 `ok`이며 건수 요약에 삽입·변경·건너뛰기 결과가 표시됩니다.

- [ ] **단계 3: DB 상태 검증**

`dbo.SSG_ORDER_ITEM`에서 `COUNT_BIG(*)`, 최신 행 수, `MAX(CollectedAt)`을 조회합니다.

예상 결과: 전체 행이 1개 이상이고 식별자마다 최신 행이 정확히 1개이며 이번 실행의 수집 시각이 NULL이 아닙니다.
