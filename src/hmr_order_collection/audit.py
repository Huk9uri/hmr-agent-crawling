"""Count-only orchestration audit persistence."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Mapping
from uuid import UUID


class ChannelLockError(RuntimeError):
    """Raised when another process owns a channel attempt lock."""

    def __init__(self, channel: str) -> None:
        self.channel = channel
        super().__init__("Channel collection is already running")


class ApplicationLock:
    """Session-owned SQL Server application lock."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def acquire(self, resource: str) -> bool:
        cursor = self._connection.cursor()
        try:
            cursor.execute(
                "DECLARE @result int; EXEC @result = sys.sp_getapplock "
                "@Resource=%s, @LockMode='Exclusive', @LockOwner='Session', @LockTimeout=0; SELECT @result",
                (resource,),
            )
            row = cursor.fetchone()
            return row is not None and int(row[0]) >= 0
        finally:
            cursor.close()

    def release(self, resource: str) -> None:
        cursor = self._connection.cursor()
        try:
            cursor.execute(
                "EXEC sys.sp_releaseapplock @Resource=%s, @LockOwner='Session'",
                (resource,),
            )
        finally:
            cursor.close()


class AuditRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def _execute(self, sql: str, params: tuple[Any, ...], *, fetch: bool = False) -> Any:
        cursor = self._connection.cursor()
        try:
            cursor.execute(sql, params)
            return cursor.fetchone() if fetch else None
        except Exception:
            self._connection.rollback()
            raise
        finally:
            cursor.close()

    def acquire_lock(self) -> bool:
        return ApplicationLock(self._connection).acquire("HMR_DAILY_ORDER_COLLECTION")

    def recover_stale_runs(self, cutoff: datetime, recovered_at: datetime) -> int:
        cursor = self._connection.cursor()
        try:
            cursor.execute(
                "UPDATE dbo.CHANNEL_COLLECTION_RUN SET FinishedAt=%s,RunStatus='ABORTED' "
                "WHERE RunStatus='RUNNING' AND StartedAt < %s",
                (recovered_at, cutoff),
            )
            count = int(cursor.rowcount)
            self._connection.commit()
            return count
        except Exception:
            self._connection.rollback()
            raise
        finally:
            cursor.close()

    def start_run(self, run_id: UUID, scheduled_date: date, started_at: datetime) -> None:
        self._execute(
            "INSERT INTO dbo.CHANNEL_COLLECTION_RUN (RunId,ScheduledDate,StartedAt,RunStatus) VALUES (%s,%s,%s,%s)",
            (str(run_id), scheduled_date, started_at, "RUNNING"),
        )
        self._connection.commit()

    def record_attempt(self, run_id: UUID, channel: str, attempt: int, started_at: datetime,
                       finished_at: datetime, status: str, counts: Mapping[str, int], error_category: str | None) -> None:
        self._execute(
            "INSERT INTO dbo.CHANNEL_COLLECTION_ATTEMPT "
            "(RunId,ChannelName,AttemptNo,StartedAt,FinishedAt,AttemptStatus,WindowsCount,PagesCount,RecordsCount,InsertedCount,ChangedCount,SkippedCount,ErrorCategory) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (str(run_id), channel, attempt, started_at, finished_at, status,
             counts.get("windows", 0), counts.get("pages", 0), counts.get("records", 0),
             counts.get("inserted", 0), counts.get("changed", 0), counts.get("skipped", 0), error_category),
        )
        self._connection.commit()

    def finish_run(self, run_id: UUID, finished_at: datetime, status: str, successful: int, failed: int) -> None:
        self._execute(
            "UPDATE dbo.CHANNEL_COLLECTION_RUN SET FinishedAt=%s,RunStatus=%s,SuccessfulChannels=%s,FailedChannels=%s WHERE RunId=%s",
            (finished_at, status, successful, failed, str(run_id)),
        )
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()
