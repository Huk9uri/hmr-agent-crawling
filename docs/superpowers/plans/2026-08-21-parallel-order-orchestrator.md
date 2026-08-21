# Parallel Order Orchestrator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run up to four independent channel collection attempts concurrently without allowing one channel's retry delay or rollback to block another channel.

**Architecture:** A central coordinator retains the existing run-level SQL application lock, submits one attempt per channel to a bounded `ThreadPoolExecutor`, records completed attempts serially, and places failed attempts in a delayed priority queue without occupying a worker. Each worker opens its own SQL connection, holds a channel-specific session application lock across read-only API collection and the channel's single write transaction, then releases all resources before returning a count-only result.

**Tech Stack:** Python 3.11+, `concurrent.futures`, SQL Server `sp_getapplock`, `pymssql`, `unittest`, Windows Task Scheduler

**Spec:** `docs/superpowers/specs/2026-08-21-parallel-order-orchestrator-design.md`

## Global Constraints

- Default concurrency is `4`; `ORCHESTRATOR_MAX_WORKERS` accepts integers from `1` through the number of registered channels.
- A retry delay must not hold a worker, channel lock, API adapter, or channel DB connection.
- The run-level lock remains held by the coordinator session for the complete run.
- `HMR_ORDER_COLLECTION:{channel}` is held only for one channel attempt and is reacquired for each retry.
- API reads complete before the channel write transaction begins; one failed record rolls back that channel attempt only.
- Audit writes are committed independently on the coordinator thread and never share a connection with workers.
- Count-only output must retain the existing statuses, error redaction, channel ordering, and exit codes; add only `FAILED_LOCK` and `ABORTED` as specified.
- No new third-party dependency is allowed.

---

### Task 1: SQL application-lock and stale-run audit primitives

**Files:**
- Modify: `src/hmr_order_collection/audit.py`
- Modify: `tests/test_audit.py`

**Interfaces:**
- Produces: `ApplicationLock(connection: Any)`, `acquire(resource: str) -> bool`, `release(resource: str) -> None`
- Produces: `AuditRepository.recover_stale_runs(cutoff: datetime, recovered_at: datetime) -> int`
- Preserves: `AuditRepository.acquire_lock() -> bool` for the run-level resource

- [ ] **Step 1: Write failing lock ownership and release tests**

Add cursor result routing and tests that assert the exact resource is passed to `sp_getapplock`, `sp_releaseapplock` is called only after successful acquisition, and a negative acquisition result returns `False` without release.

```python
lock = ApplicationLock(connection)
self.assertTrue(lock.acquire("HMR_ORDER_COLLECTION:naver"))
lock.release("HMR_ORDER_COLLECTION:naver")
self.assertEqual(connection.cursor_value.calls[0][1], ("HMR_ORDER_COLLECTION:naver",))
self.assertIn("sp_releaseapplock", connection.cursor_value.calls[1][0])
```

- [ ] **Step 2: Run the audit tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='src'
& '.venv\Scripts\python.exe' -m unittest tests.test_audit -v
```

Expected: import or attribute failure for `ApplicationLock`.

- [ ] **Step 3: Implement the session application-lock abstraction**

Use parameterized SQL only:

```python
class ApplicationLock:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def acquire(self, resource: str) -> bool:
        # EXEC sys.sp_getapplock with LockMode=Exclusive,
        # LockOwner=Session and LockTimeout=0, then return result >= 0.

    def release(self, resource: str) -> None:
        # EXEC sys.sp_releaseapplock with LockOwner=Session.
```

Make `AuditRepository.acquire_lock()` delegate to `ApplicationLock` with `HMR_DAILY_ORDER_COLLECTION` while the audit connection remains open.

- [ ] **Step 4: Write the failing stale-run recovery test**

Assert one parameterized update is committed and its row count is returned:

```python
count = repo.recover_stale_runs(cutoff, recovered_at)
self.assertEqual(count, 2)
self.assertIn("RunStatus = 'ABORTED'", cursor.calls[-1][0])
self.assertEqual(cursor.calls[-1][1], (recovered_at, cutoff))
```

- [ ] **Step 5: Implement stale-run recovery**

Update only rows satisfying `RunStatus='RUNNING' AND StartedAt < %s`, set `FinishedAt=%s` and `RunStatus='ABORTED'`, commit independently, and return `cursor.rowcount`.

- [ ] **Step 6: Run focused tests**

Run:

```powershell
$env:PYTHONPATH='src'
& '.venv\Scripts\python.exe' -m unittest tests.test_audit -v
```

Expected: all audit tests PASS.

- [ ] **Step 7: Commit**

```powershell
git add src/hmr_order_collection/audit.py tests/test_audit.py
git commit -m "feat: add channel locks and stale run recovery"
```

---

### Task 2: Attempt-level parallel coordinator

**Files:**
- Modify: `src/hmr_order_collection/orchestrator.py`
- Modify: `tests/test_orchestrator.py`

**Interfaces:**
- Changes: `orchestrate(..., max_workers: int = 4) -> tuple[int, dict[str, Any]]`
- Preserves: `execute(channel: str, run_date: date) -> dict[str, int]`
- Consumes: central `AuditRepository` methods from Task 1

- [ ] **Step 1: Replace sequential-order assertions with delayed-retry behavior tests**

With `max_workers=1`, make channel `a` fail once and channel `b` succeed. Assert execution order is `a, b, a`, proving the delayed retry does not block a ready channel.

```python
self.assertEqual(calls, ["a", "b", "a"])
self.assertEqual(sleeps, [600])
self.assertEqual([row[2] for row in audit.attempts], [1, 1, 2])
```

- [ ] **Step 2: Add a failing maximum-concurrency test**

Use `threading.Barrier(4)` and a locked active counter for eight synthetic channels. Assert `peak == 4`, all channels complete, and output order equals input channel order rather than completion order.

```python
self.assertEqual(peak, 4)
self.assertEqual([item["channel"] for item in payload["channels"]], list(channels))
```

- [ ] **Step 3: Add failing isolation and final-state tests**

Cover one permanent `FAILED_PARSE`, successful remaining channels, three attempts for the failed channel, `PARTIAL` status, exit code `1`, and absence of the exception message in payload or audit arguments.

- [ ] **Step 4: Run orchestrator tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='src'
& '.venv\Scripts\python.exe' -m unittest tests.test_orchestrator -v
```

Expected: sequential ordering and missing `max_workers` support fail.

- [ ] **Step 5: Implement the bounded attempt scheduler**

Use a ready heap ordered by `(ready_at, original_channel_index, attempt_no)`, a `Future` map, and `concurrent.futures.wait(..., return_when=FIRST_COMPLETED)`. Submit ready entries until `len(in_flight) == max_workers`. On failure, classify safely, record the attempt, and enqueue the retry time. When no future is running, sleep only until the earliest retry before submitting it; never sleep inside a worker.

Return result rows in original channel order. Preserve count keys:

```python
("windows", "pages", "records", "inserted", "changed", "skipped")
```

- [ ] **Step 6: Validate worker-count and retry arguments inside `orchestrate`**

Reject `max_workers < 1`, `max_workers > len(channels)`, negative retry count, and negative retry delay with `ValueError`. Convert `channels` to a tuple once so generators remain supported.

- [ ] **Step 7: Run focused tests**

Run:

```powershell
$env:PYTHONPATH='src'
& '.venv\Scripts\python.exe' -m unittest tests.test_orchestrator tests.test_audit -v
```

Expected: all focused tests PASS and no test sleeps for real time.

- [ ] **Step 8: Commit**

```powershell
git add src/hmr_order_collection/orchestrator.py tests/test_orchestrator.py
git commit -m "feat: schedule channel attempts in parallel"
```

---

### Task 3: Independent worker connections, channel locks, and configuration

**Files:**
- Modify: `src/hmr_order_collection/orchestrator.py`
- Modify: `src/hmr_order_collection/config.py`
- Modify: `.env.example`
- Modify: `tests/test_orchestrator.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Produces: `AppConfig.orchestrator_max_workers(channel_count: int) -> int`
- Produces: `_executor(config_path: Path, connection_factory=connect_from_config) -> Callable[[str, date], dict[str, int]]`
- Consumes: `ApplicationLock` from Task 1

- [ ] **Step 1: Write failing configuration tests**

Test absent value returns 4, values `1`, `4`, and `8` are accepted for eight channels, and `0`, `9`, non-integer, and blank values raise `ConfigurationError` without echoing the supplied value.

```python
self.assertEqual(config({}).orchestrator_max_workers(8), 4)
self.assertEqual(config({"ORCHESTRATOR_MAX_WORKERS": "8"}).orchestrator_max_workers(8), 8)
```

- [ ] **Step 2: Add the environment template key**

Append:

```env
ORCHESTRATOR_MAX_WORKERS=4
```

- [ ] **Step 3: Implement strict worker-count parsing**

Add the `AppConfig.orchestrator_max_workers` method with a sanitized `ConfigurationError("ORCHESTRATOR_MAX_WORKERS must be an integer between 1 and the channel count")` for all invalid cases.

- [ ] **Step 4: Write failing executor resource-boundary tests**

Inject connection and adapter factories. Assert each attempt receives a new connection, acquires `HMR_ORDER_COLLECTION:{channel}` before adapter fetch, commits or rolls back only its own writer transaction, releases the lock, and closes the connection on success, API failure, parse failure, and DB failure.

- [ ] **Step 5: Implement the locked channel attempt executor**

For each `execute(channel, run_date)` call:

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

`ChannelLockError` must have a constant message without embedding connection details and map to `FAILED_LOCK`.

- [ ] **Step 6: Wire startup recovery and max workers in `main`**

After acquiring the run lock and before `start_run`, call `recover_stale_runs(now - timedelta(hours=3), now)`. Read `max_workers` from config and pass it to `orchestrate`. Preserve CLI flags and JSON shape.

- [ ] **Step 7: Run focused tests**

Run:

```powershell
$env:PYTHONPATH='src'
& '.venv\Scripts\python.exe' -m unittest tests.test_orchestrator tests.test_audit tests.test_cli -v
```

Expected: all focused tests PASS.

- [ ] **Step 8: Commit**

```powershell
git add .env.example src/hmr_order_collection/config.py src/hmr_order_collection/orchestrator.py tests/test_orchestrator.py tests/test_cli.py
git commit -m "feat: isolate channel attempts with configured workers"
```

---

### Task 4: Apply channel locks to manual write commands

**Files:**
- Modify: `src/hmr_order_collection/cli.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Consumes: `ApplicationLock` and `ChannelLockError` from Tasks 1 and 3
- Preserves: dry-run commands open no DB connection and acquire no lock
- Preserves: write-mode count-only JSON and sanitized failures

- [ ] **Step 1: Write failing manual-write lock tests**

For `collect --write-db`, assert the channel lock is acquired before `writer.write`, released afterward, and the connection closes. Add failure cases for lock denial and writer exception. For `--dry-run`, assert no lock factory or DB connection is used.

- [ ] **Step 2: Run CLI tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='src'
& '.venv\Scripts\python.exe' -m unittest tests.test_cli -v
```

Expected: no channel lock calls are observed.

- [ ] **Step 3: Implement channel lock boundaries in write mode**

Acquire and release `HMR_ORDER_COLLECTION:{channel}` around the existing writer call. In `collect-all`, release one channel lock before proceeding to the next. Never acquire locks for dry-run or boundary probing.

- [ ] **Step 4: Run CLI and database regression tests**

Run:

```powershell
$env:PYTHONPATH='src'
& '.venv\Scripts\python.exe' -m unittest tests.test_cli tests.test_database -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/hmr_order_collection/cli.py tests/test_cli.py
git commit -m "feat: lock manual channel writes"
```

---

### Task 5: Operations documentation and end-to-end verification

**Files:**
- Modify: `docs/daily-order-collection-operations.md`
- Modify: `docs/channel-order-tables.md`
- Modify: `tests/test_windows_scheduler_scripts.py`

**Interfaces:**
- Preserves: `scripts/windows/run_daily_order_collection.ps1` invocation and exit-code propagation
- Documents: `ORCHESTRATOR_MAX_WORKERS=4`, per-channel locks, nonblocking retries, `ABORTED`, and rollback via worker count 1

- [ ] **Step 1: Add a scheduler compatibility assertion**

Keep the existing assertion that the launcher invokes `-m hmr_order_collection.orchestrator`; additionally assert it does not hard-code a worker count, so `.env` remains authoritative.

- [ ] **Step 2: Update operations documentation**

Document:

```text
maximum four concurrent channel attempts
retry waiting does not occupy a worker
channel-specific transaction and application lock
ORCHESTRATOR_MAX_WORKERS=1 emergency sequential fallback
ABORTED stale-run recovery after three hours
```

Include SQL examples ordering attempts by `StartedAt` to confirm overlapping channel execution without exposing order data.

- [ ] **Step 3: Run the complete test suite**

Run:

```powershell
$env:PYTHONPATH='src'
& '.venv\Scripts\python.exe' -m unittest discover -s tests -v
```

Expected: all tests PASS.

- [ ] **Step 4: Run static change checks**

Run:

```powershell
git diff --check
git status --short
```

Expected: no whitespace errors and only intended files changed.

- [ ] **Step 5: Perform local SQL lock and dry-run integration checks**

Run one local orchestrator invocation with `ORCHESTRATOR_MAX_WORKERS=4` and retry delay `0` against configured read-only channel APIs and the development SQL Server. Verify count-only output, four-or-fewer overlapping attempt intervals, independent channel results, no plaintext PII, and correct final exit code. Do not run this against production until the user confirms deployment timing.

- [ ] **Step 6: Commit**

```powershell
git add docs/daily-order-collection-operations.md docs/channel-order-tables.md tests/test_windows_scheduler_scripts.py
git commit -m "docs: document parallel collection operations"
```

- [ ] **Step 7: Prepare server deployment handoff**

List the exact changed runtime files, `.env` addition, unchanged Windows task registration, SQL verification query, and manual validation command. Do not copy to or modify the server without explicit authorization.
