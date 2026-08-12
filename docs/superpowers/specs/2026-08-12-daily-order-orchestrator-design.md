# Daily Order Collection Orchestrator Design

## Goal

Run every currently supported production order collector once per day through a single orchestration entrypoint, isolate channel failures, retry transient failures, and persist a count-only audit trail that can later drive email alerts. Prepare Windows Task Scheduler scripts locally, but do not register a task until working on the actual server PC.

## Scope

The daily run includes the seven deployed adapters: Naver SmartStore, Godomall, Coupang, LotteON, 11st, SSG.COM, and Toss Shopping. CJ OnStyle, Gmarket/Auction, and AliExpress remain excluded because production access or implemented collectors are not available.

SMTP delivery and the 14:30 missing-run watchdog are deferred until a corporate SMTP account is available. The execution-history schema must make both additions possible without changing collector behavior.

## Architecture

Add a dedicated orchestration command alongside the existing collection CLI. It runs each channel independently with that channel's verified maximum safe window ending on the run date. A failure never prevents later channels from running.

Each failed channel is retried up to two times after a configurable delay. Tests inject a no-wait sleep function; production defaults to ten minutes. Successful empty API responses are recorded separately from failures.

A run-level row and one channel-attempt row per attempt are written to SQL Server. Audit rows contain identifiers, timestamps, status, counts, attempt number, and a sanitized error category only. They never contain credentials, URLs with query strings, response bodies, order identifiers, personal data, or exception messages.

## Status model

Run status:

- `RUNNING`: orchestration started but has not reached a terminal state.
- `SUCCESS`: every channel ended in `SUCCESS_WITH_DATA` or `SUCCESS_EMPTY`.
- `PARTIAL`: at least one channel succeeded and at least one channel failed after retries.
- `FAILED`: no channel succeeded, or orchestration could not initialize.

Channel-attempt status:

- `SUCCESS_WITH_DATA`: API and database write succeeded with one or more collected records.
- `SUCCESS_EMPTY`: API succeeded and returned zero records.
- `FAILED_API`: HTTP transport or remote business response failure.
- `FAILED_PARSE`: response decoding, validation, or mapping failure.
- `FAILED_DB`: database connection or persistence failure.
- `FAILED_CONFIG`: required configuration was unavailable or invalid.
- `FAILED_INTERNAL`: an unexpected sanitized failure category.

## Database schema

Create `dbo.CHANNEL_COLLECTION_RUN` for one daily orchestration execution and `dbo.CHANNEL_COLLECTION_ATTEMPT` for channel attempts. Foreign-key channel attempts to the run. Index the run scheduled date and terminal status, and index channel/date/status queries needed by a future watchdog.

The orchestrator uses a separate audit connection from channel data writers. Attempt audit writes are committed independently so a channel transaction rollback does not erase evidence of failure. If audit persistence itself fails, the process exits nonzero and writes a count-only JSON summary to standard output.

## Concurrency and exit behavior

Use a SQL Server application lock keyed to the daily orchestrator. If another process holds the lock, exit nonzero without starting collectors. This prevents a manual run and the scheduled run from overlapping across Windows sessions.

Exit code is zero only when all channels reach a success state. Partial and failed runs return nonzero so Windows Task Scheduler records a failure result.

## Windows integration

Provide two PowerShell scripts:

- A launcher that resolves absolute project, Python, configuration, and log paths; sets `PYTHONPATH`; runs the orchestrator; and preserves its exit code.
- An installer that validates prerequisites and creates a daily 14:00 task on the machine where it is executed.

The installer defaults to the Windows `SYSTEM` account so the job runs while users are logged out. It must refuse installation when paths are missing and must support a validation mode that prints the intended task definition without changing Task Scheduler.

Task Scheduler registration is deliberately not executed on the local development PC. It will be run and validated after remote access to the actual server PC.

## Verification

Use test-driven development for status classification, retries, channel isolation, audit writes, application-lock behavior, safe output, PowerShell argument construction, and task-definition validation. Run the full existing Python test suite plus focused PowerShell-safe static/behavioral tests. Apply the SQL migration to the current development/operating database only after its idempotency and schema-contract tests pass.
