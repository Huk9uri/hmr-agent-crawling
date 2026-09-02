# 네이버·롯데ON 최근 30일 수동 백필 업무 일지

- 작업일: 2026-09-02
- 목적: 기존 일일 증분 수집을 유지하면서 최근 30일 주문상품을 운영자가 최초 1회 적재하거나 누락 구간을 복구할 수 있도록 보완
- 상태 관리: 별도 상태·체크포인트 테이블을 추가하지 않음

## 적용 방식

공통 CLI 명령 `backfill`을 추가했다. 지원 채널은 `naver`, `lotteon`이며 조회기간은 최대 30일이다. `--cutoff`는 exclusive 자정 경계다. 예를 들어 `--cutoff 2026-09-02 --days 30`은 2026-08-03 00:00 이상 2026-09-02 00:00 미만에 해당하는 완료된 날짜 30개를 오래된 날짜부터 조회한다.

백필은 운영자가 수동으로 실행한다. Windows 작업 스케줄러의 매일 14:00 수집은 기존 증분 방식 그대로 유지되며, 백필 명령을 자동 스케줄에 등록하지 않는다.

## 네이버

- API: 조건형 상품 주문 상세 내역 조회
- 조회 기준: `ORDERED_DATETIME`
- 분할: KST 기준 24시간 구간 30개
- 페이지: 응답의 `pagination.hasNext`가 거짓이 될 때까지 `page` 증가
- 요청 경계: `00:00:00.000`부터 다음 날 `00:00:00.000`까지 inclusive로 호출
- 중복 처리: 페이지 내부와 날짜 경계에서 반복된 `ProductOrderId`를 제거

날짜 경계를 의도적으로 공유하므로 자정에 정확히 걸린 상품주문이 양쪽 요청에 포함될 수 있다. 모든 날짜 결과를 합친 뒤 `ProductOrderId`로 한 번 더 중복 제거하므로 동일 상품주문은 DB writer에 한 번만 전달된다.

## 롯데ON

- API: 기존 배포된 출고·회수지시 주문정보 조회 및 배송상태 조회
- 분할: KST 달력 날짜 1일 구간 30개
- 주문 포함 범위: 출고·회수지시 조회를 `ifCplYN=N`, `ifCplYN=Y`로 각각 호출하고 합침
- 중복 처리: 모든 날짜 결과를 합친 뒤 배포된 주문상품 identity로 제거
- 안전 조건: 상태 변경 API는 호출하지 않으며 기존 두 읽기 전용 조회만 사용

공식 명세상 `ifCplYN`을 생략하면 신규 생성 주문만 조회된다. 따라서 백필에서는 신규·미완료 범위인 `N`과 연동완료 범위인 `Y`를 모두 조회하고 같은 주문상품이 양쪽에 나타나면 identity로 한 번만 유지한다.

이번 범위에는 배송상태 워터마크, 미완료 주문 추적 큐, 체크포인트 테이블 및 별도 반복 스케줄을 포함하지 않았다.

## 적재와 재실행

`--dry-run`은 API 조회와 건수 집계만 수행하고 DB에 쓰지 않는다. `--write-db`는 기존 `HMR_ORDER_COLLECTION:{channel}` 애플리케이션 잠금을 획득한 뒤 중복 제거된 전체 결과를 한 번의 채널 쓰기로 전달한다.

DB writer는 주문상품 identity와 payload hash를 비교한다.

- 처음 확인한 주문상품: `inserted`
- 기존 최신 내용과 달라진 주문상품: 변경 이력 적재
- 기존 최신 내용과 같은 주문상품: `skipped`

따라서 운영자가 같은 백필 명령을 다시 실행해도 동일 payload의 중복 이력이 생성되지 않는다. 다만 외부 상태 테이블이 없으므로 성공 여부는 실행 결과와 감사 이력으로 확인하고 업무 일지에 기록해야 한다.

## 운영 명령

먼저 두 채널을 각각 dry-run 한다.

```powershell
$env:PYTHONPATH='C:\Users\Administrator\Desktop\iyeon_RPA\HMR_Agent_Crawling\src'
$PythonExe='C:\Users\Administrator\Desktop\iyeon_RPA\HMR_Agent_Crawling\.venv\Scripts\python.exe'
$ConfigPath='C:\Users\Administrator\Desktop\iyeon_RPA\HMR_Agent_Crawling\.env'

& $PythonExe -m hmr_order_collection.cli backfill `
  --channel naver --cutoff 2026-09-02 --days 30 `
  --dry-run --config $ConfigPath

& $PythonExe -m hmr_order_collection.cli backfill `
  --channel lotteon --cutoff 2026-09-02 --days 30 `
  --dry-run --config $ConfigPath
```

두 결과 모두 `status`가 `ok`이면 동일 명령에서 `--dry-run`만 `--write-db`로 바꿔 실제 적재한다.

## 자동 검증

- 네이버 조건형 조회의 요청 파라미터와 inclusive 경계
- 네이버 `hasNext` 다중 페이지 처리
- 네이버 페이지 내부 `ProductOrderId` 중복 제거
- 30개 날짜 전체 identity 중복 제거
- 롯데ON 기존 읽기 전용 조회만 재사용
- 허용되지 않은 채널 및 1~30일 범위 밖 입력 거부
- 기존 정기 수집 회귀 테스트

## 운영키 dry-run 결과

`--cutoff 2026-09-02 --days 30` 조건으로 DB 쓰기 없이 최종 CLI를 검증했다.

| 채널 | 날짜 구간 | API 응답 페이지/요청 | 중복 제거 후 주문상품 | 결과 |
|---|---:|---:|---:|---|
| 네이버 | 30 | 46 | 8,097 | 성공 |
| 롯데ON | 30 | 90 | 1 | 성공 |

롯데ON 90회는 날짜별 `ifCplYN=N`, `ifCplYN=Y`, 배송상태 조회 각 1회씩이다. 두 dry-run 모두 DB 연결과 저장을 수행하지 않았다. 전체 자동 테스트는 129건 통과했다.
