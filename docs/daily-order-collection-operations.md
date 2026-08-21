# Daily Order Collection Operations

## What is automated

The orchestrator runs the eight deployed channels independently: Naver SmartStore, Godomall, Coupang, LotteON, 11st, SSG.COM, CJ OnStyle, and Toss Shopping. By default it runs no more than four channel attempts concurrently. A failed attempt is returned to a delayed retry queue, so its ten-minute wait does not occupy a worker or block another ready channel. Every attempt is recorded in SQL Server, and the process returns nonzero when any channel remains failed.

Each attempt opens its own SQL connection and holds `HMR_ORDER_COLLECTION:{channel}` from API collection through that channel's single database transaction. The lock is released as soon as the attempt finishes. Consequently, a failure rolls back only that channel's write, and a manual write cannot overlap the scheduled write for the same channel. The coordinator holds the existing run-wide lock for the complete scheduled run.

Email notification and the separate missing-run watchdog will be added after a corporate SMTP account is issued.

## Server prerequisites

- Copy or clone the project onto the actual collection server PC.
- Install Python 3.12 and `pip install -r requirements.txt` in a stable server-owned virtual environment.
- Place `.env` outside source control and restrict it to Administrators and `SYSTEM`.
- Set `ORCHESTRATOR_MAX_WORKERS=4` in `.env`. Accepted values are 1 through the registered channel count.
- Confirm the server's public IP is the IP registered with every marketplace.
- Confirm `SYSTEM` can read the project, Python executable, `.env`, and write the log directory.
- Apply `080_create_collection_audit_tables.sql` and run `085_verify_collection_audit_tables.sql`.

## Manual run

```powershell
$env:PYTHONPATH='C:\HMR_Agent_Crawling\src'
& 'C:\HMR_Agent_Crawling\.venv\Scripts\python.exe' -m hmr_order_collection.orchestrator --config 'C:\HMR_Agent_Crawling\.env'
```

The output contains status and counts only. Exit code `0` means all channels succeeded. Exit code `1` means partial or total channel failure. Exit code `2` means initialization failure or an overlapping run.

## Validate and register the 14:00 task

Run validation first; it never changes Task Scheduler:

```powershell
& .\scripts\windows\install_daily_order_collection_task.ps1 `
  -ProjectRoot 'C:\HMR_Agent_Crawling' `
  -PythonExe 'C:\HMR_Agent_Crawling\.venv\Scripts\python.exe' `
  -ConfigPath 'C:\HMR_Agent_Crawling\.env' `
  -ValidateOnly
```

After checking the resolved paths, run the same command as Administrator without `-ValidateOnly`. The task runs daily at 14:00 as `SYSTEM`, starts when a missed schedule becomes available, rejects overlapping instances, and has a three-hour execution limit.

Use Task Scheduler to run the task once manually. Confirm its last result is `0`, a count-only log appears under `C:\ProgramData\HMR_Order_Collection\logs`, and audit rows appear in SQL Server.

## Audit queries

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

`SUCCESS_EMPTY` means the API succeeded but returned no orders. It is not a failure. `FAILED_API`, `FAILED_PARSE`, `FAILED_DB`, `FAILED_CONFIG`, and `FAILED_INTERNAL` require investigation.

`FAILED_LOCK` means the channel was already being collected by another scheduled or manual process. A `RUNNING` audit row older than three hours is changed to `ABORTED` when the next run obtains the run-wide lock. This recovery changes audit state only; it does not undo API reads or already committed channel transactions.

To temporarily return to sequential operation during incident response, set `ORCHESTRATOR_MAX_WORKERS=1` and run the same launcher. No Windows Task Scheduler registration change is required because the launcher intentionally does not hard-code a worker count.

To confirm overlap is bounded and retries do not block other channels, compare attempt intervals for one run:

```sql
SELECT ChannelName, AttemptNo, AttemptStatus, StartedAt, FinishedAt,
       DATEDIFF(second, StartedAt, FinishedAt) AS DurationSeconds
FROM dbo.CHANNEL_COLLECTION_ATTEMPT
WHERE RunId = '00000000-0000-0000-0000-000000000000'
ORDER BY StartedAt, ChannelName, AttemptNo;
```

Replace the sample `RunId` with a value from `CHANNEL_COLLECTION_RUN`. Overlapping `StartedAt`/`FinishedAt` intervals show parallel execution; no more than the configured worker count should overlap.

## Remove the task

```powershell
Unregister-ScheduledTask -TaskName 'HMR Daily Order Collection' -Confirm:$false
```

Removing the task does not delete audit history or collected orders.
