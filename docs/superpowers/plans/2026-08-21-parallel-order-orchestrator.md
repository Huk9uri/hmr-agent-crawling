# 병렬 주문 오케스트레이터 구현 계획

> **에이전트 작업자 안내:** 필수 하위 스킬로 superpowers:subagent-driven-development(권장) 또는 superpowers:executing-plans를 사용하여 이 계획을 작업별로 구현합니다. 진행 상황은 체크박스(`- [ ]`)로 추적합니다.

**목표:** 채널 하나의 재시도 대기나 롤백이 다른 채널을 막지 않도록 독립적인 채널 수집 시도를 최대 4개 동시에 실행합니다.

**구조:** 중앙 조정자는 기존 실행 단위 SQL 애플리케이션 잠금을 유지하면서 제한된 `ThreadPoolExecutor`에 채널별 시도를 제출합니다. 완료 시도는 순차 기록하고 실패 시도는 작업 스레드를 점유하지 않는 지연 우선순위 큐에 넣습니다. 각 작업 스레드는 별도 SQL 연결을 열고 읽기 전용 API 수집부터 해당 채널의 단일 저장 트랜잭션까지 채널별 세션 애플리케이션 잠금을 유지한 뒤 모든 자원을 해제하고 건수 중심 결과를 반환합니다.

**기술 스택:** Python 3.11+, `concurrent.futures`, SQL Server `sp_getapplock`, `pymssql`, `unittest`, Windows 작업 스케줄러.

**명세:** `docs/superpowers/specs/2026-08-21-parallel-order-orchestrator-design.md`

## 공통 제약 사항

- 기본 동시 실행 수는 `4`이며 `ORCHESTRATOR_MAX_WORKERS`는 `1`부터 등록 채널 수까지의 정수를 허용합니다.
- 재시도 대기 중 작업 스레드, 채널 잠금, API 어댑터, 채널 DB 연결을 유지하지 않습니다.
- 전체 실행 동안 조정자 세션이 실행 단위 잠금을 유지합니다.
- `HMR_ORDER_COLLECTION:{channel}`은 채널 시도 하나에만 유지하며 재시도마다 다시 획득합니다.
- API 조회를 끝낸 뒤 채널 저장 트랜잭션을 시작합니다. 레코드 하나의 실패는 해당 채널 시도만 롤백합니다.
- 감사 저장은 조정자 스레드에서 독립 커밋하며 작업 스레드와 연결을 공유하지 않습니다.
- 건수 중심 출력은 기존 상태·오류 마스킹·채널 순서·종료 코드를 유지하고 명세에 따라 `FAILED_LOCK`과 `ABORTED`만 추가합니다.
- 새 외부 의존성을 추가하지 않습니다.

---

### 작업 1: SQL 애플리케이션 잠금 및 오래된 실행 복구 기반 기능

**파일:**
- 수정: `src/hmr_order_collection/audit.py`
- 수정: `tests/test_audit.py`

**인터페이스:**
- 산출물: `ApplicationLock(connection: Any)`, `acquire(resource: str) -> bool`, `release(resource: str) -> None`
- 산출물: `AuditRepository.recover_stale_runs(cutoff: datetime, recovered_at: datetime) -> int`
- 유지: 실행 단위 자원에 대한 `AuditRepository.acquire_lock() -> bool`

- [ ] **단계 1: 실패하는 잠금 소유·해제 테스트 작성**

커서 결과 분기와 테스트를 추가하여 `sp_getapplock`에 정확한 자원이 전달되고, 획득 성공 후에만 `sp_releaseapplock`이 호출되며, 획득 결과가 음수이면 해제 없이 `False`를 반환하는지 확인합니다.

```python
lock = ApplicationLock(connection)
self.assertTrue(lock.acquire("HMR_ORDER_COLLECTION:naver"))
lock.release("HMR_ORDER_COLLECTION:naver")
self.assertEqual(connection.cursor_value.calls[0][1], ("HMR_ORDER_COLLECTION:naver",))
self.assertIn("sp_releaseapplock", connection.cursor_value.calls[1][0])
```

- [ ] **단계 2: 감사 테스트 실행 및 실패 확인**

실행:

```powershell
$env:PYTHONPATH='src'
& '.venv\Scripts\python.exe' -m unittest tests.test_audit -v
```

예상 결과: `ApplicationLock` 가져오기 또는 속성 조회에 실패합니다.

- [ ] **단계 3: 세션 애플리케이션 잠금 추상화 구현**

매개변수화된 SQL만 사용합니다:

```python
class ApplicationLock:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def acquire(self, resource: str) -> bool:
        # LockMode=Exclusive, LockOwner=Session, LockTimeout=0으로
        # EXEC sys.sp_getapplock을 실행하고 result >= 0을 반환합니다.

    def release(self, resource: str) -> None:
        # LockOwner=Session으로 EXEC sys.sp_releaseapplock을 실행합니다.
```

감사 연결이 열려 있는 동안 `AuditRepository.acquire_lock()`이 `HMR_DAILY_ORDER_COLLECTION`을 자원으로 `ApplicationLock`에 위임하도록 합니다.

- [ ] **단계 4: 실패하는 오래된 실행 복구 테스트 작성**

매개변수화된 갱신 한 번이 커밋되고 행 수가 반환되는지 검증합니다:

```python
count = repo.recover_stale_runs(cutoff, recovered_at)
self.assertEqual(count, 2)
self.assertIn("RunStatus = 'ABORTED'", cursor.calls[-1][0])
self.assertEqual(cursor.calls[-1][1], (recovered_at, cutoff))
```

- [ ] **단계 5: 오래된 실행 복구 구현**

`RunStatus='RUNNING' AND StartedAt < %s`인 행만 갱신하여 `FinishedAt=%s`, `RunStatus='ABORTED'`를 설정합니다. 독립 커밋하고 `cursor.rowcount`를 반환합니다.

- [ ] **단계 6: 대상 테스트 실행**

실행:

```powershell
$env:PYTHONPATH='src'
& '.venv\Scripts\python.exe' -m unittest tests.test_audit -v
```

예상 결과: 모든 감사 테스트가 통과합니다.

- [ ] **단계 7: 커밋**

```powershell
git add src/hmr_order_collection/audit.py tests/test_audit.py
git commit -m "feat: add channel locks and stale run recovery"
```

---

### 작업 2: 시도 단위 병렬 조정자

**파일:**
- 수정: `src/hmr_order_collection/orchestrator.py`
- 수정: `tests/test_orchestrator.py`

**인터페이스:**
- 변경: `orchestrate(..., max_workers: int = 4) -> tuple[int, dict[str, Any]]`
- 유지: `execute(channel: str, run_date: date) -> dict[str, int]`
- 입력: 작업 1의 중앙 `AuditRepository` 메서드

- [ ] **단계 1: 순차 실행 순서 단언을 지연 재시도 동작 테스트로 교체**

`max_workers=1`에서 채널 `a`는 한 번 실패하고 채널 `b`는 성공하도록 만듭니다. 실행 순서가 `a, b, a`인지 검증하여 지연 재시도가 준비된 채널을 막지 않는지 확인합니다.

```python
self.assertEqual(calls, ["a", "b", "a"])
self.assertEqual(sleeps, [600])
self.assertEqual([row[2] for row in audit.attempts], [1, 1, 2])
```

- [ ] **단계 2: 실패하는 최대 동시 실행 수 테스트 추가**

8개 가상 채널에 `threading.Barrier(4)`와 잠금으로 보호된 활성 작업 계수를 사용합니다. `peak == 4`이고 모든 채널이 완료되며, 출력 순서는 완료 순서가 아닌 입력 채널 순서인지 확인합니다.

```python
self.assertEqual(peak, 4)
self.assertEqual([item["channel"] for item in payload["channels"]], list(channels))
```

- [ ] **단계 3: 실패하는 격리 및 최종 상태 테스트 추가**

영구적인 `FAILED_PARSE` 하나와 나머지 채널 성공, 실패 채널의 3회 시도, `PARTIAL` 상태, 종료 코드 `1`, 결과 및 감사 인자에 예외 메시지가 없는지를 검증합니다.

- [ ] **단계 4: 오케스트레이터 테스트 실행 및 실패 확인**

실행:

```powershell
$env:PYTHONPATH='src'
& '.venv\Scripts\python.exe' -m unittest tests.test_orchestrator -v
```

예상 결과: 순차 실행 순서와 `max_workers` 지원 누락 때문에 실패합니다.

- [ ] **단계 5: 동시 실행 수가 제한된 시도 스케줄러 구현**

`(ready_at, original_channel_index, attempt_no)` 순서의 준비 힙, `Future` 매핑, `concurrent.futures.wait(..., return_when=FIRST_COMPLETED)`를 사용합니다. `len(in_flight) == max_workers`가 될 때까지 준비된 항목을 제출합니다. 실패 시 안전하게 분류하고 시도를 기록한 뒤 재시도 시각을 큐에 넣습니다. 실행 중인 future가 없으면 가장 빠른 재시도 시각까지만 대기하고 제출하며 작업 스레드 안에서는 대기하지 않습니다.

결과 행은 원래 채널 순서로 반환하며 다음 건수 키를 유지합니다:

```python
("windows", "pages", "records", "inserted", "changed", "skipped")
```

- [ ] **단계 6: `orchestrate` 내부에서 작업 스레드 수·재시도 인자 검증**

`max_workers < 1`, `max_workers > len(channels)`, 음수 재시도 횟수, 음수 재시도 대기 시간을 `ValueError`로 거부합니다. 제너레이터 지원을 유지하도록 `channels`는 한 번만 튜플로 변환합니다.

- [ ] **단계 7: 대상 테스트 실행**

실행:

```powershell
$env:PYTHONPATH='src'
& '.venv\Scripts\python.exe' -m unittest tests.test_orchestrator tests.test_audit -v
```

예상 결과: 대상 테스트가 모두 통과하고 실제 시간 대기를 수행하는 테스트는 없습니다.

- [ ] **단계 8: 커밋**

```powershell
git add src/hmr_order_collection/orchestrator.py tests/test_orchestrator.py
git commit -m "feat: schedule channel attempts in parallel"
```

---

### 작업 3: 독립 작업 연결·채널 잠금·설정

**파일:**
- 수정: `src/hmr_order_collection/orchestrator.py`
- 수정: `src/hmr_order_collection/config.py`
- 수정: `.env.example`
- 수정: `tests/test_orchestrator.py`
- 수정: `tests/test_cli.py`

**인터페이스:**
- 산출물: `AppConfig.orchestrator_max_workers(channel_count: int) -> int`
- 산출물: `_executor(config_path: Path, connection_factory=connect_from_config) -> Callable[[str, date], dict[str, int]]`
- 입력: 작업 1의 `ApplicationLock`

- [ ] **단계 1: 실패하는 설정 테스트 작성**

값이 없으면 4를 반환하고 8개 채널에서 `1`, `4`, `8`을 허용하는지 테스트합니다. `0`, `9`, 정수가 아닌 값, 빈 값은 입력값을 노출하지 않고 `ConfigurationError`를 발생시켜야 합니다.

```python
self.assertEqual(config({}).orchestrator_max_workers(8), 4)
self.assertEqual(config({"ORCHESTRATOR_MAX_WORKERS": "8"}).orchestrator_max_workers(8), 8)
```

- [ ] **단계 2: 환경 설정 템플릿 키 추가**

다음 항목을 추가합니다:

```env
ORCHESTRATOR_MAX_WORKERS=4
```

- [ ] **단계 3: 엄격한 작업 스레드 수 파싱 구현**

`AppConfig.orchestrator_max_workers`를 추가하고 모든 잘못된 입력에 민감정보가 없는 `ConfigurationError("ORCHESTRATOR_MAX_WORKERS must be an integer between 1 and the channel count")`를 사용합니다.

- [ ] **단계 4: 실패하는 실행기 자원 경계 테스트 작성**

연결·어댑터 팩토리를 주입합니다. 성공·API 실패·파싱 실패·DB 실패 각각에 대해 새 연결을 사용하고 어댑터 조회 전에 `HMR_ORDER_COLLECTION:{channel}`을 획득하며, 자기 저장 트랜잭션만 커밋·롤백하고 잠금 해제와 연결 종료를 수행하는지 확인합니다.

- [ ] **단계 5: 잠금을 사용하는 채널 시도 실행기 구현**

각 `execute(channel, run_date)` 호출은 다음과 같이 처리합니다:

```python
connection = connection_factory(config)
resource = f"HMR_ORDER_COLLECTION:{channel}"
lock = ApplicationLock(connection)
try:
    if not lock.acquire(resource):
        raise ChannelLockError(channel)
    adapter = registry_builder(config)[channel]
    records = list(adapter.fetch(window))
    written = writer_factory(connection).write(channel, records, uuid4())
    return count_only_result
finally:
    if acquired:
        lock.release(resource)
    connection.close()
```

`ChannelLockError`는 연결 상세를 포함하지 않는 고정 메시지를 사용하고 `FAILED_LOCK`으로 분류해야 합니다.

- [ ] **단계 6: `main`에 시작 시 복구 및 최대 작업 수 연결**

실행 잠금 획득 후 `start_run` 전에 `recover_stale_runs(now - timedelta(hours=3), now)`를 호출합니다. 설정에서 `max_workers`를 읽어 `orchestrate`에 전달하고 CLI 플래그와 JSON 구조를 유지합니다.

- [ ] **단계 7: 대상 테스트 실행**

실행:

```powershell
$env:PYTHONPATH='src'
& '.venv\Scripts\python.exe' -m unittest tests.test_orchestrator tests.test_audit tests.test_cli -v
```

예상 결과: 모든 대상 테스트가 통과합니다.

- [ ] **단계 8: 커밋**

```powershell
git add .env.example src/hmr_order_collection/config.py src/hmr_order_collection/orchestrator.py tests/test_orchestrator.py tests/test_cli.py
git commit -m "feat: isolate channel attempts with configured workers"
```

---

### 작업 4: 수동 저장 명령에 채널 잠금 적용

**파일:**
- 수정: `src/hmr_order_collection/cli.py`
- 수정: `tests/test_cli.py`

**인터페이스:**
- 입력: 작업 1·3의 `ApplicationLock`, `ChannelLockError`
- 유지: dry-run은 DB 연결을 열거나 잠금을 획득하지 않습니다.
- 유지: 저장 모드의 건수 중심 JSON과 민감정보가 제거된 실패 정보

- [ ] **단계 1: 실패하는 수동 저장 잠금 테스트 작성**

`collect --write-db`에서 `writer.write` 전에 채널 잠금을 획득하고 이후 해제한 뒤 연결을 닫는지 확인합니다. 잠금 거부와 저장기 예외 사례를 추가합니다. `--dry-run`은 잠금 팩토리나 DB 연결을 사용하지 않아야 합니다.

- [ ] **단계 2: CLI 테스트 실행 및 실패 확인**

실행:

```powershell
$env:PYTHONPATH='src'
& '.venv\Scripts\python.exe' -m unittest tests.test_cli -v
```

예상 결과: 채널 잠금 호출이 관찰되지 않습니다.

- [ ] **단계 3: 저장 모드의 채널 잠금 경계 구현**

기존 저장기 호출 전후로 `HMR_ORDER_COLLECTION:{channel}`을 획득·해제합니다. `collect-all`은 다음 채널로 넘어가기 전에 현재 채널 잠금을 해제합니다. dry-run과 경계 탐색에서는 잠금을 획득하지 않습니다.

- [ ] **단계 4: CLI 및 DB 회귀 테스트 실행**

실행:

```powershell
$env:PYTHONPATH='src'
& '.venv\Scripts\python.exe' -m unittest tests.test_cli tests.test_database -v
```

예상 결과: 모든 대상 테스트가 통과합니다.

- [ ] **단계 5: 커밋**

```powershell
git add src/hmr_order_collection/cli.py tests/test_cli.py
git commit -m "feat: lock manual channel writes"
```

---

### 작업 5: 운영 문서 및 통합 검증

**파일:**
- 수정: `docs/daily-order-collection-operations.md`
- 수정: `docs/channel-order-tables.md`
- 수정: `tests/test_windows_scheduler_scripts.py`

**인터페이스:**
- 유지: `scripts/windows/run_daily_order_collection.ps1` 호출 방식과 종료 코드 전달
- 문서화: `ORCHESTRATOR_MAX_WORKERS=4`, 채널별 잠금, 다른 작업을 막지 않는 재시도, `ABORTED`, 작업 수 1을 통한 순차 실행 복귀

- [ ] **단계 1: 스케줄러 호환성 단언 추가**

실행 스크립트가 `-m hmr_order_collection.orchestrator`를 호출하는 기존 단언을 유지합니다. 작업 수를 코드에 고정하지 않아 `.env`가 기준이 되는지도 추가로 확인합니다.

- [ ] **단계 2: 운영 문서 갱신**

다음 내용을 문서화합니다:

```text
채널 시도 최대 4개 동시 실행
재시도 대기 중 작업 스레드를 점유하지 않음
채널별 독립 트랜잭션과 애플리케이션 잠금
ORCHESTRATOR_MAX_WORKERS=1로 비상 시 순차 실행 복귀
3시간 경과한 오래된 실행을 ABORTED로 복구
```

주문 데이터를 노출하지 않고 채널 실행이 겹치는지 확인하도록 시도를 `StartedAt`순으로 조회하는 SQL 예시를 포함합니다.

- [ ] **단계 3: 전체 테스트 실행**

실행:

```powershell
$env:PYTHONPATH='src'
& '.venv\Scripts\python.exe' -m unittest discover -s tests -v
```

예상 결과: 모든 대상 테스트가 통과합니다.

- [ ] **단계 4: 변경 사항 정적 검사 실행**

실행:

```powershell
git diff --check
git status --short
```

예상 결과: 공백 오류가 없고 의도한 파일만 변경되었습니다.

- [ ] **단계 5: 로컬 SQL 잠금 및 dry-run 통합 점검 수행**

설정된 읽기 전용 채널 API와 개발 SQL Server를 대상으로 `ORCHESTRATOR_MAX_WORKERS=4`, 재시도 대기 시간 `0`으로 로컬 오케스트레이터를 한 번 실행합니다. 건수 중심 출력, 최대 4개까지 겹치는 시도 구간, 독립 채널 결과, 개인정보 평문 부재 및 최종 종료 코드를 확인합니다. 사용자가 배포 시점을 확인하기 전에는 운영 환경에서 실행하지 않습니다.

- [ ] **단계 6: 커밋**

```powershell
git add docs/daily-order-collection-operations.md docs/channel-order-tables.md tests/test_windows_scheduler_scripts.py
git commit -m "docs: document parallel collection operations"
```

- [ ] **단계 7: 서버 배포 인계 준비**

변경된 실행 파일의 정확한 목록, `.env` 추가 항목, Windows 작업 등록 변경 없음, SQL 검증 쿼리 및 수동 검증 명령을 정리합니다. 명시적 승인 없이 서버에 복사하거나 서버를 변경하지 않습니다.
