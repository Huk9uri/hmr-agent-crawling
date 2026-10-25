# 일일 주문 수집 운영 가이드

## 자동화 범위

오케스트레이터는 배포된 8개 채널인 네이버 스마트스토어, 고도몰, 쿠팡, 롯데ON, 11번가, SSG.COM, CJ온스타일, 토스쇼핑을 독립적으로 실행합니다. 기본 동시 실행 수는 최대 4개입니다. 실패한 시도는 지연 재시도 큐로 돌아가므로 10분 대기 중에도 작업 스레드를 점유하거나 실행 가능한 다른 채널을 막지 않습니다. 모든 시도는 SQL Server에 기록하며, 최종 실패 채널이 있으면 0이 아닌 종료 코드를 반환합니다.

각 시도는 별도 SQL 연결을 열고 API 수집부터 해당 채널의 단일 DB 트랜잭션이 끝날 때까지 `HMR_ORDER_COLLECTION:{channel}` 잠금을 유지합니다. 시도가 끝나면 즉시 잠금을 해제합니다. 따라서 실패 시 해당 채널의 저장만 롤백되며, 같은 채널의 수동 저장과 예약 저장이 겹치지 않습니다. 조정자는 정기 실행 전체가 끝날 때까지 기존 전체 실행 잠금을 유지합니다.

이메일 알림과 별도의 미실행 감시 기능은 회사 SMTP 계정 발급 후 추가할 예정입니다.

## 서버 사전 준비

- 실제 수집 서버 PC에 프로젝트를 복사하거나 복제합니다.
- 서버에서 안정적으로 관리할 가상환경에 Python 3.12를 설치하고 `pip install -r requirements.txt`를 실행합니다.
- `.env`를 버전 관리에서 제외하고 Administrators와 `SYSTEM`만 접근하도록 제한합니다.
- `.env`에 `ORCHESTRATOR_MAX_WORKERS=4`를 설정합니다. 허용 범위는 1부터 등록된 채널 수까지입니다.
- 서버의 공인 IP가 각 쇼핑몰에 등록된 IP와 일치하는지 확인합니다.
- `SYSTEM`이 프로젝트, Python 실행 파일, `.env`를 읽고 로그 디렉터리에 쓸 수 있는지 확인합니다.
- `080_create_collection_audit_tables.sql`을 적용하고 `085_verify_collection_audit_tables.sql`을 실행합니다.

## 수동 실행

```powershell
$env:PYTHONPATH='C:\HMR_Agent_Crawling\src'
& 'C:\HMR_Agent_Crawling\.venv\Scripts\python.exe' -m hmr_order_collection.orchestrator --config 'C:\HMR_Agent_Crawling\.env'
```

출력에는 상태와 건수만 포함됩니다. 종료 코드 `0`은 전체 성공, `1`은 일부 또는 전체 채널 실패, `2`는 초기화 실패 또는 실행 중복을 뜻합니다.

## 네이버·롯데ON 일회성 과거 데이터 보충

일일 스케줄러는 증분 수집을 유지합니다. 최근 완료된 30일을 초기 적재하거나 복구해야 할 때 아래 수동 명령을 한 번 실행합니다. `--cutoff 2026-09-02`는 `2026-09-02 00:00:00 KST` 직전까지의 30개 일별 조회 구간을 의미하며, 대상 날짜는 2026-08-03부터 2026-09-01까지입니다.

먼저 읽기 전용 API 호출로 검증합니다:

```powershell
$env:PYTHONPATH='C:\HMR_Agent_Crawling\src'
& 'C:\HMR_Agent_Crawling\.venv\Scripts\python.exe' `
  -m hmr_order_collection.cli backfill `
  --channel naver --cutoff 2026-09-02 --days 30 --dry-run `
  --config 'C:\HMR_Agent_Crawling\.env'

& 'C:\HMR_Agent_Crawling\.venv\Scripts\python.exe' `
  -m hmr_order_collection.cli backfill `
  --channel lotteon --cutoff 2026-09-02 --days 30 --dry-run `
  --config 'C:\HMR_Agent_Crawling\.env'
```

두 결과가 모두 `status: ok`이면 각 명령의 `--dry-run`을 `--write-db`로 바꾸어 다시 실행합니다. 저장 모드는 기존 채널별 애플리케이션 잠금을 획득합니다. 네이버는 `pagination.hasNext`를 따라 조회하며 `ORDERED_DATETIME`을 사용합니다. 롯데ON은 배포된 읽기 전용 주문 검색을 `ifCplYN=N`, `ifCplYN=Y` 각각 호출해 결과를 합치고, 읽기 전용 배송 진행 검색 결과를 결합합니다. 두 채널 모두 API 조회 구간을 하루로 나누고, 배포된 주문상품 식별자로 전체 반환 레코드의 중복을 제거한 뒤 한 번에 DB에 저장합니다. 완료된 보충 수집을 다시 실행해도 DB의 페이로드 해시 비교로 변경 없는 레코드는 건너뜁니다.

명령은 영구적인 완료 표시를 생성하지 않습니다. 저장 성공 결과를 배포 기록에 남기고 이 명령을 Windows 작업 스케줄러에 추가하지 않습니다. 기존 14:00 작업은 계속 증분 수집만 실행합니다.

## 14:00 작업 검증 및 등록

먼저 검증을 실행합니다. 검증 모드는 작업 스케줄러를 변경하지 않습니다:

```powershell
& .\scripts\windows\install_daily_order_collection_task.ps1 `
  -ProjectRoot 'C:\HMR_Agent_Crawling' `
  -PythonExe 'C:\HMR_Agent_Crawling\.venv\Scripts\python.exe' `
  -ConfigPath 'C:\HMR_Agent_Crawling\.env' `
  -ValidateOnly
```

확정된 경로를 확인한 후 관리자 권한으로 같은 명령에서 `-ValidateOnly`를 제외하고 실행합니다. 작업은 매일 14:00에 `SYSTEM`으로 실행됩니다. 놓친 예약은 실행 가능한 시점에 시작하며, 중복 실행을 막고 실행 시간을 3시간으로 제한합니다.

작업 스케줄러에서 작업을 한 번 수동 실행합니다. 마지막 실행 결과가 `0`인지, `C:\ProgramData\HMR_Order_Collection\logs`에 건수 중심 로그가 생성되는지, SQL Server에 감사 행이 기록되는지 확인합니다.

## 감사 이력 조회

```sql
SELECT TOP (30) ScheduledDate, StartedAt, FinishedAt, RunStatus,
       SuccessfulChannels, FailedChannels
FROM dbo.CHANNEL_COLLECTION_RUN
ORDER BY StartedAt DESC;

SELECT TOP (100) r.ScheduledDate, a.ChannelName, a.AttemptNo,
       a.AttemptStatus, a.RecordsCount, a.InsertedCount,
       a.ChangedCount, a.SkippedCount, a.ErrorCategory,
       a.StartedAt, a.FinishedAt
FROM dbo.CHANNEL_COLLECTION_ATTEMPT AS a
JOIN dbo.CHANNEL_COLLECTION_RUN AS r ON r.RunId = a.RunId
ORDER BY a.StartedAt DESC;
```

`SUCCESS_EMPTY`는 API 호출은 성공했지만 주문이 없음을 의미하며 실패가 아닙니다. `FAILED_API`, `FAILED_PARSE`, `FAILED_DB`, `FAILED_CONFIG`, `FAILED_INTERNAL`은 원인을 조사해야 합니다.

`FAILED_LOCK`은 다른 예약 또는 수동 프로세스가 이미 해당 채널을 수집 중임을 뜻합니다. 3시간보다 오래된 `RUNNING` 감사 행은 다음 실행이 전체 실행 잠금을 획득할 때 `ABORTED`로 변경됩니다. 이 복구는 감사 상태만 변경하며 API 조회나 이미 커밋된 채널 트랜잭션을 되돌리지 않습니다.

장애 대응 중 일시적으로 순차 실행으로 돌아가려면 `ORCHESTRATOR_MAX_WORKERS=1`로 설정하고 같은 실행 스크립트를 사용합니다. 실행 스크립트에 작업 스레드 수를 고정하지 않으므로 Windows 작업 스케줄러를 다시 등록할 필요가 없습니다.

동시 실행 수가 제한되고 재시도가 다른 채널을 막지 않는지 확인하려면 한 실행의 시도 시간 구간을 비교합니다:

```sql
SELECT ChannelName, AttemptNo, AttemptStatus, StartedAt, FinishedAt,
       DATEDIFF(second, StartedAt, FinishedAt) AS DurationSeconds
FROM dbo.CHANNEL_COLLECTION_ATTEMPT
WHERE RunId = '00000000-0000-0000-0000-000000000000'
ORDER BY StartedAt, ChannelName, AttemptNo;
```

예시 `RunId`를 `CHANNEL_COLLECTION_RUN`의 실제 값으로 바꿉니다. `StartedAt`과 `FinishedAt` 사이 구간이 겹치면 병렬 실행을 뜻하며, 겹치는 수는 설정된 작업 스레드 수를 넘지 않아야 합니다.

## 작업 해제

```powershell
Unregister-ScheduledTask -TaskName 'HMR Daily Order Collection' -Confirm:$false
```

작업을 해제해도 감사 이력과 수집된 주문은 삭제되지 않습니다.
