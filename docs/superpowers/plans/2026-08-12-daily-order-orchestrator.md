# Daily Order Collection Orchestrator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a locally verified seven-channel daily collector with retry, durable count-only audit history, overlap protection, and server-ready Windows Task Scheduler scripts.

**Architecture:** A new Python orchestration module reuses the deployed adapters and `DatabaseWriter`, but owns channel isolation, retry, status classification, and audit persistence. SQL Server application locks prevent overlap. PowerShell scripts only launch and install the tested Python entrypoint; task registration remains deferred until execution on the server PC.

**Tech Stack:** Python 3.12, `unittest`, `pymssql`, SQL Server T-SQL, Windows PowerShell 5.1, Windows Task Scheduler.

## Global Constraints

- Include only `naver`, `godomall`, `coupang`, `lotteon`, `elevenst`, `ssg`, and `toss`.
- Never persist or print credentials, response bodies, order identifiers, personal data, URLs with query strings, or exception messages.
- Retry each failed channel at most two times after the initial attempt; production delay is 600 seconds.
- Use a separate committed audit transaction from each channel data transaction.
- Return exit code zero only when all seven channels succeed.
- Do not register a Windows scheduled task on the local development PC.
- The server installer must target a daily 14:00 schedule and default to the `SYSTEM` account.

---

### Task 1: Create idempotent audit schema

**Files:**
- Create: `sql/channel_orders/080_create_collection_audit_tables.sql`
- Create: `sql/channel_orders/085_verify_collection_audit_tables.sql`
- Create: `tests/test_collection_audit_sql.py`

**Interfaces:**
- Produces: `dbo.CHANNEL_COLLECTION_RUN` and `dbo.CHANNEL_COLLECTION_ATTEMPT` with foreign key and watchdog indexes.

- [ ] **Step 1: Write the failing SQL contract test**

Assert that the migration defines run identity, scheduled date, UTC start/end, run status, channel, attempt number, count columns, sanitized error category, foreign key, unique `(RunId, ChannelName, AttemptNo)`, and idempotent guards. Assert that the verifier checks the same deployed contract.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `python -m unittest tests.test_collection_audit_sql -v`

Expected: FAIL because both SQL files are missing.

- [ ] **Step 3: Implement the migration and verifier**

Use `IF OBJECT_ID(...) IS NULL` guards, `datetime2(3)`, `date`, bounded `nvarchar` statuses, integer count columns, and `SYSUTCDATETIME()` defaults. Create indexes supporting scheduled-date/status and channel/date/status lookups.

- [ ] **Step 4: Verify GREEN and SQL syntax**

Run: `python -m unittest tests.test_collection_audit_sql -v`

Run both scripts with `sqlcmd -b` against the configured database, then run the migration a second time.

Expected: test passes; both migration runs and verifier exit zero.

- [ ] **Step 5: Commit**

```powershell
git add -- sql/channel_orders/080_create_collection_audit_tables.sql sql/channel_orders/085_verify_collection_audit_tables.sql tests/test_collection_audit_sql.py
git commit -m "feat: add collection audit tables"
```

### Task 2: Implement audit repository and overlap lock

**Files:**
- Create: `src/hmr_order_collection/audit.py`
- Create: `tests/test_audit.py`

**Interfaces:**
- Produces: `AuditRepository.acquire_lock() -> bool`, `start_run(...)`, `record_attempt(...)`, `finish_run(...)`, and `close()`.
- Consumes: a DB-API-compatible `pymssql` connection.

- [ ] **Step 1: Write failing repository behavior tests**

Cover successful and rejected `sp_getapplock`, independent commits for run/attempt/final updates, rollback on audit failure, parameterized values, and cursor closure. Tests assert SQL effects rather than internal helper calls.

- [ ] **Step 2: Run and verify RED**

Run: `python -m unittest tests.test_audit -v`

Expected: import failure because `audit.py` does not exist.

- [ ] **Step 3: Implement the minimal repository**

Use static SQL identifiers, `%s` parameters, `LockOwner='Session'`, zero lock timeout, UTC-aware timestamps, and one commit per audit event. Convert UUIDs to strings at the driver boundary.

- [ ] **Step 4: Verify GREEN**

Run: `python -m unittest tests.test_audit -v`

Expected: all audit tests pass.

- [ ] **Step 5: Commit**

```powershell
git add -- src/hmr_order_collection/audit.py tests/test_audit.py
git commit -m "feat: persist collection audit history"
```

### Task 3: Implement channel-isolated orchestration

**Files:**
- Create: `src/hmr_order_collection/orchestrator.py`
- Create: `tests/test_orchestrator.py`

**Interfaces:**
- Produces: `run_daily(config_path: Path, run_date: date, retry_attempts: int = 2, retry_delay_seconds: int = 600, ...) -> tuple[int, dict[str, Any]]` and `main(argv=None) -> int`.
- Consumes: existing adapter registry, maximum-window calculation, `DatabaseWriter`, and `AuditRepository`.

- [ ] **Step 1: Write failing orchestration tests**

Cover seven-channel order, safe maximum windows, success-with-data, success-empty, API/parse/DB/config/internal classification, two retries, sleep only between attempts, later-channel continuation, partial/failed/success aggregation, nonzero overlap exit, and count-only JSON output.

- [ ] **Step 2: Run and verify RED**

Run: `python -m unittest tests.test_orchestrator -v`

Expected: import failure because `orchestrator.py` does not exist.

- [ ] **Step 3: Implement minimal orchestration**

Create fresh adapter and data connection per channel attempt, calculate `start = run_date - timedelta(days=MAXIMUM_WINDOW_DAYS[channel] - 1)`, write through `DatabaseWriter`, record every attempt, close resources, and render only safe counts and categories.

- [ ] **Step 4: Verify focused and full Python suite**

Run: `python -m unittest tests.test_orchestrator -v`

Run: `python -m unittest discover -s tests -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add -- src/hmr_order_collection/orchestrator.py tests/test_orchestrator.py
git commit -m "feat: orchestrate daily channel collection"
```

### Task 4: Add server launcher and scheduler installer

**Files:**
- Create: `scripts/windows/run_daily_order_collection.ps1`
- Create: `scripts/windows/install_daily_order_collection_task.ps1`
- Create: `tests/test_windows_scheduler_scripts.py`
- Modify: `.env.example`

**Interfaces:**
- Produces: launcher parameters `ProjectRoot`, `PythonExe`, `ConfigPath`, and `LogDirectory`; installer parameters with `ValidateOnly` and daily `14:00` task definition.

- [ ] **Step 1: Write failing PowerShell contract tests**

Assert absolute-path validation, `PYTHONPATH` setup, orchestrator module invocation, exit-code preservation, log directory creation, `SYSTEM` principal, daily trigger at `14:00`, overlap prevention, nonzero-result visibility, and `ValidateOnly` behavior. Assert no plaintext secrets in either script.

- [ ] **Step 2: Run and verify RED**

Run: `python -m unittest tests.test_windows_scheduler_scripts -v`

Expected: FAIL because scripts are missing.

- [ ] **Step 3: Implement scripts and example settings**

The launcher invokes `python -m hmr_order_collection.orchestrator --config <absolute path>` and writes count-only stdout/stderr logs. The installer uses `New-ScheduledTaskAction`, `New-ScheduledTaskTrigger -Daily -At '14:00'`, `New-ScheduledTaskPrincipal -UserId 'SYSTEM'`, and `New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew`; `ValidateOnly` returns the resolved definition without calling `Register-ScheduledTask`.

- [ ] **Step 4: Verify scripts locally without registration**

Run: `python -m unittest tests.test_windows_scheduler_scripts -v`

Run the installer with `-ValidateOnly` and explicit existing local paths.

Expected: tests pass and validation reports a 14:00 SYSTEM task; no task is registered.

- [ ] **Step 5: Commit**

```powershell
git add -- scripts/windows/run_daily_order_collection.ps1 scripts/windows/install_daily_order_collection_task.ps1 tests/test_windows_scheduler_scripts.py .env.example
git commit -m "feat: prepare Windows daily collection task"
```

### Task 5: Document and perform final local verification

**Files:**
- Create: `docs/daily-order-collection-operations.md`

**Interfaces:**
- Produces: server installation checklist, manual run procedure, audit queries, status meanings, rollback/unregister command, and deferred SMTP/watchdog handoff.

- [ ] **Step 1: Write the operations guide**

Document prerequisites, server-only registration, `SYSTEM` permissions, `.env` protection, 14:00 task validation, manual count-only output checks, SQL audit queries, rerun behavior, and safe removal with `Unregister-ScheduledTask`.

- [ ] **Step 2: Run fresh verification**

Run: `python -m unittest discover -s tests -v`

Run: `git diff --check`

Run the audit verifier with `sqlcmd -b`.

Run the installer only with `-ValidateOnly`.

Expected: zero test failures, clean diff check, valid audit schema, and no local scheduled task registration.

- [ ] **Step 3: Commit**

```powershell
git add -- docs/daily-order-collection-operations.md
git commit -m "docs: add daily collection operations guide"
```
