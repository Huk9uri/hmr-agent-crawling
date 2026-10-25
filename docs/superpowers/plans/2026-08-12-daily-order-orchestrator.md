# 일일 주문 수집 오케스트레이터 구현 계획

> **에이전트 작업자 안내:** 필수 하위 스킬로 superpowers:subagent-driven-development(권장) 또는 superpowers:executing-plans를 사용하여 이 계획을 작업별로 구현합니다. 진행 상황은 체크박스(`- [ ]`)로 추적합니다.

**목표:** 재시도, 영구적인 건수 중심 감사 이력, 중복 실행 방지 및 서버용 Windows 작업 스케줄러 스크립트를 갖춘 7개 채널 일일 수집기를 로컬에서 검증합니다.

**구조:** 새 Python 오케스트레이션 모듈이 배포된 어댑터와 `DatabaseWriter`를 재사용하며 채널 격리, 재시도, 상태 분류, 감사 이력 저장을 담당합니다. SQL Server 애플리케이션 잠금으로 중복 실행을 방지합니다. PowerShell 스크립트는 검증된 Python 진입점을 실행·설치하며 실제 작업 등록은 서버 PC에서 수행할 때까지 미룹니다.

**기술 스택:** Python 3.12, `unittest`, `pymssql`, SQL Server T-SQL, Windows PowerShell 5.1, Windows 작업 스케줄러.

## 공통 제약 사항

- `naver`, `godomall`, `coupang`, `lotteon`, `elevenst`, `ssg`, `toss`만 포함합니다.
- 인증 정보, 응답 본문, 주문 식별자, 개인정보, 쿼리 문자열을 포함한 URL, 예외 메시지는 저장하거나 출력하지 않습니다.
- 최초 시도 후 실패 채널을 최대 두 번 재시도하며 운영 대기 시간은 600초입니다.
- 감사 트랜잭션은 각 채널 데이터 트랜잭션과 분리하여 커밋합니다.
- 7개 채널이 모두 성공한 경우에만 종료 코드 0을 반환합니다.
- 로컬 개발 PC에는 Windows 예약 작업을 등록하지 않습니다.
- 서버 설치 스크립트는 매일 14:00 실행과 기본 `SYSTEM` 계정을 사용합니다.

---

### 작업 1: 멱등성을 갖춘 감사 스키마 생성

**파일:**
- 생성: `sql/channel_orders/080_create_collection_audit_tables.sql`
- 생성: `sql/channel_orders/085_verify_collection_audit_tables.sql`
- 생성: `tests/test_collection_audit_sql.py`

**인터페이스:**
- 산출물: 외래 키와 감시용 인덱스를 갖춘 `dbo.CHANNEL_COLLECTION_RUN`, `dbo.CHANNEL_COLLECTION_ATTEMPT`.

- [ ] **단계 1: 실패하는 SQL 계약 테스트 작성**

마이그레이션이 실행 식별자, 예약 날짜, UTC 시작·종료 시각, 실행 상태, 채널, 시도 번호, 건수 컬럼, 민감정보를 제거한 오류 분류, 외래 키, `(RunId, ChannelName, AttemptNo)` 유일성 및 멱등성 검사를 정의하는지 확인합니다. 검증 스크립트도 동일한 배포 계약을 검사해야 합니다.

- [ ] **단계 2: 대상 테스트 실행 및 실패 확인**

실행: `python -m unittest tests.test_collection_audit_sql -v`

예상 결과: SQL 파일 두 개가 모두 없어 실패합니다.

- [ ] **단계 3: 마이그레이션 및 검증 스크립트 구현**

`IF OBJECT_ID(...) IS NULL` 검사, `datetime2(3)`, `date`, 길이가 제한된 `nvarchar` 상태, 정수 건수 컬럼, `SYSUTCDATETIME()` 기본값을 사용합니다. 예약 날짜·상태 및 채널·날짜·상태 조회용 인덱스를 생성합니다.

- [ ] **단계 4: 테스트 통과 및 SQL 구문 확인**

실행: `python -m unittest tests.test_collection_audit_sql -v`

설정된 DB에서 `sqlcmd -b`로 두 스크립트를 실행한 뒤 마이그레이션을 한 번 더 실행합니다.

예상 결과: 테스트가 통과하고 두 마이그레이션 실행과 검증 스크립트가 종료 코드 0을 반환합니다.

- [ ] **단계 5: 커밋**

```powershell
git add -- sql/channel_orders/080_create_collection_audit_tables.sql sql/channel_orders/085_verify_collection_audit_tables.sql tests/test_collection_audit_sql.py
git commit -m "feat: add collection audit tables"
```

### 작업 2: 감사 저장소 및 중복 실행 잠금 구현

**파일:**
- 생성: `src/hmr_order_collection/audit.py`
- 생성: `tests/test_audit.py`

**인터페이스:**
- 산출물: `AuditRepository.acquire_lock() -> bool`, `start_run(...)`, `record_attempt(...)`, `finish_run(...)`, `close()`.
- 입력: DB-API 호환 `pymssql` 연결.

- [ ] **단계 1: 실패하는 저장소 동작 테스트 작성**

`sp_getapplock` 성공·거부, 실행·시도·최종 갱신의 독립 커밋, 감사 실패 시 롤백, 매개변수화된 값, 커서 종료를 검증합니다. 내부 보조 함수 호출보다 SQL의 효과를 확인합니다.

- [ ] **단계 2: 실행 및 실패 확인**

실행: `python -m unittest tests.test_audit -v`

예상 결과: `audit.py`가 없어 가져오기에 실패합니다.

- [ ] **단계 3: 최소 저장소 구현**

고정 SQL 식별자, `%s` 매개변수, `LockOwner='Session'`, 잠금 대기 시간 0, UTC 시간대 정보가 있는 시각 및 감사 이벤트당 한 번의 커밋을 사용합니다. 드라이버 경계에서 UUID를 문자열로 변환합니다.

- [ ] **단계 4: 통과 상태 확인**

실행: `python -m unittest tests.test_audit -v`

예상 결과: 모든 감사 테스트가 통과합니다.

- [ ] **단계 5: 커밋**

```powershell
git add -- src/hmr_order_collection/audit.py tests/test_audit.py
git commit -m "feat: persist collection audit history"
```

### 작업 3: 채널 격리 오케스트레이션 구현

**파일:**
- 생성: `src/hmr_order_collection/orchestrator.py`
- 생성: `tests/test_orchestrator.py`

**인터페이스:**
- 산출물: `run_daily(config_path: Path, run_date: date, retry_attempts: int = 2, retry_delay_seconds: int = 600, ...) -> tuple[int, dict[str, Any]]`, `main(argv=None) -> int`.
- 입력: 기존 어댑터 레지스트리, 최대 조회 기간 계산, `DatabaseWriter`, `AuditRepository`.

- [ ] **단계 1: 실패하는 오케스트레이션 테스트 작성**

7개 채널 순서, 안전한 최대 조회 기간, 데이터 있는 성공·빈 성공, API·파싱·DB·설정·내부 오류 분류, 두 번 재시도, 시도 사이에만 대기, 후속 채널 계속 실행, 부분 성공·실패·성공 집계, 중복 실행의 0이 아닌 종료 코드 및 건수 중심 JSON 출력을 검증합니다.

- [ ] **단계 2: 실행 및 실패 확인**

실행: `python -m unittest tests.test_orchestrator -v`

예상 결과: `orchestrator.py`가 없어 가져오기에 실패합니다.

- [ ] **단계 3: 최소 오케스트레이션 구현**

채널 시도마다 새 어댑터와 데이터 연결을 만들고 `start = run_date - timedelta(days=MAXIMUM_WINDOW_DAYS[channel] - 1)`을 계산합니다. `DatabaseWriter`로 저장하고 모든 시도를 기록하며 자원을 닫은 후 안전한 건수와 분류만 출력합니다.

- [ ] **단계 4: 대상 테스트 및 전체 Python 테스트 검증**

실행: `python -m unittest tests.test_orchestrator -v`

실행: `python -m unittest discover -s tests -v`

예상 결과: 모든 대상 테스트가 통과합니다.

- [ ] **단계 5: 커밋**

```powershell
git add -- src/hmr_order_collection/orchestrator.py tests/test_orchestrator.py
git commit -m "feat: orchestrate daily channel collection"
```

### 작업 4: 서버 실행 스크립트 및 스케줄러 설치 스크립트 추가

**파일:**
- 생성: `scripts/windows/run_daily_order_collection.ps1`
- 생성: `scripts/windows/install_daily_order_collection_task.ps1`
- 생성: `tests/test_windows_scheduler_scripts.py`
- 수정: `.env.example`

**인터페이스:**
- 산출물: 실행 스크립트 매개변수 `ProjectRoot`, `PythonExe`, `ConfigPath`, `LogDirectory`와, `ValidateOnly` 및 매일 `14:00` 작업 정의를 지원하는 설치 스크립트 매개변수.

- [ ] **단계 1: 실패하는 PowerShell 계약 테스트 작성**

절대 경로 검증, `PYTHONPATH` 설정, 오케스트레이터 모듈 실행, 종료 코드 보존, 로그 디렉터리 생성, `SYSTEM` 실행 계정, 매일 `14:00` 트리거, 중복 실행 방지, 0이 아닌 결과 확인 및 `ValidateOnly` 동작을 검증합니다. 두 스크립트에 비밀정보 평문이 없는지도 확인합니다.

- [ ] **단계 2: 실행 및 실패 확인**

실행: `python -m unittest tests.test_windows_scheduler_scripts -v`

예상 결과: 스크립트가 없어 실패합니다.

- [ ] **단계 3: 스크립트 및 설정 예시 구현**

실행 스크립트는 `python -m hmr_order_collection.orchestrator --config <absolute path>`를 호출하고 상태·건수 중심의 표준 출력·오류 로그를 기록합니다. 설치 스크립트는 `New-ScheduledTaskAction`, `New-ScheduledTaskTrigger -Daily -At '14:00'`, `New-ScheduledTaskPrincipal -UserId 'SYSTEM'`, `New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew`를 사용합니다. `ValidateOnly`는 `Register-ScheduledTask`를 호출하지 않고 확정된 정의만 반환합니다.

- [ ] **단계 4: 등록 없이 로컬에서 스크립트 검증**

실행: `python -m unittest tests.test_windows_scheduler_scripts -v`

실제로 존재하는 로컬 경로를 명시하고 `-ValidateOnly`로 설치 스크립트를 실행합니다.

예상 결과: 테스트가 통과하고 검증 결과에 14:00 SYSTEM 작업이 표시되며 실제 작업은 등록되지 않습니다.

- [ ] **단계 5: 커밋**

```powershell
git add -- scripts/windows/run_daily_order_collection.ps1 scripts/windows/install_daily_order_collection_task.ps1 tests/test_windows_scheduler_scripts.py .env.example
git commit -m "feat: prepare Windows daily collection task"
```

### 작업 5: 문서화 및 최종 로컬 검증

**파일:**
- 생성: `docs/daily-order-collection-operations.md`

**인터페이스:**
- 산출물: 서버 설치 점검 목록, 수동 실행 절차, 감사 조회, 상태 의미, 롤백·등록 해제 명령 및 후속 SMTP·미실행 감시 인계 내용.

- [ ] **단계 1: 운영 가이드 작성**

사전 조건, 서버에서만 수행하는 등록, `SYSTEM` 권한, `.env` 보호, 14:00 작업 검증, 수동 실행의 건수 출력 확인, SQL 감사 조회, 재실행 동작 및 `Unregister-ScheduledTask`로 안전하게 해제하는 방법을 문서화합니다.

- [ ] **단계 2: 새로 검증 실행**

실행: `python -m unittest discover -s tests -v`

실행: `git diff --check`

`sqlcmd -b`로 감사 검증 스크립트를 실행합니다.

설치 스크립트는 `-ValidateOnly`로만 실행합니다.

예상 결과: 테스트 실패와 공백 오류가 없고 감사 스키마가 유효하며 로컬 예약 작업이 등록되지 않습니다.

- [ ] **단계 3: 커밋**

```powershell
git add -- docs/daily-order-collection-operations.md
git commit -m "docs: add daily collection operations guide"
```
