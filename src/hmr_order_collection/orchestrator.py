"""Daily, channel-isolated order collection orchestration."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Iterable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from datetime import date, datetime, timedelta, timezone
import heapq
import json
from pathlib import Path
import sys
import time
from typing import Any
from uuid import uuid4

from hmr_order_collection.audit import ApplicationLock, AuditRepository, ChannelLockError
from hmr_order_collection.channels import CHANNEL_NAMES, MAXIMUM_WINDOW_DAYS, build_adapter_registry
from hmr_order_collection.channels.base import DateWindow
from hmr_order_collection.config import ConfigurationError, load_config
from hmr_order_collection.database import DatabaseWriter, connect_from_config
from hmr_order_collection.http import HttpResponseError


def _category(error: Exception) -> str:
    if isinstance(error, ChannelLockError): return "FAILED_LOCK"
    if isinstance(error, ConfigurationError): return "FAILED_CONFIG"
    if isinstance(error, HttpResponseError): return "FAILED_API"
    if isinstance(error, (ValueError, TypeError, KeyError)): return "FAILED_PARSE"
    if error.__class__.__module__.startswith("pymssql"): return "FAILED_DB"
    return "FAILED_INTERNAL"


def orchestrate(*, channels: Iterable[str], run_date: date, audit: Any,
                execute: Callable[[str, date], dict[str, int]], sleep: Callable[[float], None],
                retry_attempts: int = 2, retry_delay_seconds: int = 600,
                max_workers: int = 4, lock_already_acquired: bool = False) -> tuple[int, dict[str, Any]]:
    channels = tuple(channels)
    if max_workers < 1 or max_workers > len(channels):
        raise ValueError("max_workers must be between 1 and the channel count")
    if retry_attempts < 0:
        raise ValueError("retry_attempts must not be negative")
    if retry_delay_seconds < 0:
        raise ValueError("retry_delay_seconds must not be negative")
    if not lock_already_acquired and not audit.acquire_lock():
        return 2, {"status": "ALREADY_RUNNING", "channels": []}
    run_id = uuid4()
    audit.start_run(run_id, run_date, datetime.now(timezone.utc))

    count_keys = ("windows", "pages", "records", "inserted", "changed", "skipped")
    final_results: dict[str, dict[str, Any]] = {}
    logical_now = time.monotonic()
    ready: list[tuple[float, int, int]] = [
        (logical_now, index, 1) for index in range(len(channels))
    ]
    heapq.heapify(ready)
    in_flight: dict[Future[dict[str, int]], tuple[int, int, datetime]] = {}

    pool = ThreadPoolExecutor(max_workers=max_workers)
    try:
        while ready or in_flight:
            logical_now = max(logical_now, time.monotonic())
            while ready and ready[0][0] <= logical_now and len(in_flight) < max_workers:
                _, index, attempt = heapq.heappop(ready)
                started = datetime.now(timezone.utc)
                future = pool.submit(execute, channels[index], run_date)
                in_flight[future] = (index, attempt, started)

            if not in_flight:
                next_ready = ready[0][0]
                delay = max(0.0, next_ready - logical_now)
                sleep(delay)
                logical_now = next_ready
                continue

            timeout = None
            if ready and len(in_flight) < max_workers:
                timeout = max(0.0, ready[0][0] - logical_now)
            completed, _ = wait(in_flight, timeout=timeout, return_when=FIRST_COMPLETED)
            for future in completed:
                index, attempt, started = in_flight.pop(future)
                channel = channels[index]
                try:
                    counts = future.result()
                    status = "SUCCESS_WITH_DATA" if counts.get("records", 0) else "SUCCESS_EMPTY"
                    category = None
                except Exception as error:
                    counts = {}
                    status = category = _category(error)
                finished = datetime.now(timezone.utc)
                audit.record_attempt(run_id, channel, attempt, started, finished, status, counts, category)
                final_results[channel] = {
                    "channel": channel,
                    "status": status,
                    "attempts": attempt,
                    **{key: counts.get(key, 0) for key in count_keys},
                }
                if not status.startswith("SUCCESS_") and attempt <= retry_attempts:
                    retry_at = max(logical_now, time.monotonic()) + retry_delay_seconds
                    heapq.heappush(ready, (retry_at, index, attempt + 1))
    except BaseException:
        for future in in_flight:
            future.cancel()
        pool.shutdown(wait=False, cancel_futures=True)
        successful = sum(
            item["status"].startswith("SUCCESS_") for item in final_results.values()
        )
        audit.finish_run(
            run_id, datetime.now(timezone.utc), "ABORTED",
            successful, len(channels) - successful,
        )
        raise
    else:
        pool.shutdown(wait=True)

    results = [final_results[channel] for channel in channels]
    successful = sum(item["status"].startswith("SUCCESS_") for item in results)
    failed = len(results) - successful
    status = "SUCCESS" if not failed else "PARTIAL" if successful else "FAILED"
    audit.finish_run(run_id, datetime.now(timezone.utc), status, successful, failed)
    return (0 if not failed else 1), {"status": status, "channels": results}


def _executor(
    config_path: Path,
    *,
    connection_factory: Callable[[Any], Any] = connect_from_config,
    registry_builder: Callable[[Any], dict[str, Any]] = build_adapter_registry,
    writer_factory: Callable[[Any], Any] = DatabaseWriter,
) -> Callable[[str, date], dict[str, int]]:
    config = load_config(config_path)
    def execute(channel: str, run_date: date) -> dict[str, int]:
        connection = connection_factory(config)
        resource = f"HMR_ORDER_COLLECTION:{channel}"
        lock = ApplicationLock(connection)
        acquired = False
        result: dict[str, int] | None = None
        primary_error: BaseException | None = None
        try:
            acquired = lock.acquire(resource)
            if not acquired:
                raise ChannelLockError(channel)
            adapter = registry_builder(config)[channel]
            start = run_date - timedelta(days=MAXIMUM_WINDOW_DAYS[channel] - 1)
            records = list(adapter.fetch(DateWindow(start, run_date)))
            written = writer_factory(connection).write(channel, records, uuid4())
            result = {"windows": 1, "pages": adapter.pages_fetched, "records": len(records),
                      "inserted": written.inserted, "changed": written.changed, "skipped": written.skipped}
        except BaseException as error:
            primary_error = error

        cleanup_error: BaseException | None = None
        try:
            if acquired:
                lock.release(resource)
        except BaseException as error:
            cleanup_error = error
        try:
            connection.close()
        except BaseException as error:
            if cleanup_error is None:
                cleanup_error = error

        if primary_error is not None:
            raise primary_error
        if cleanup_error is not None:
            raise cleanup_error
        if result is None:
            raise RuntimeError("Channel attempt produced no result")
        return result
    return execute


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m hmr_order_collection.orchestrator")
    parser.add_argument("--config", type=Path, default=Path(".env"))
    parser.add_argument("--date", type=date.fromisoformat, default=date.today())
    parser.add_argument("--retry-attempts", type=int, default=2)
    parser.add_argument("--retry-delay-seconds", type=int, default=600)
    args = parser.parse_args(argv)
    audit = None
    try:
        config = load_config(args.config)
        audit = AuditRepository(connect_from_config(config))
        if not audit.acquire_lock():
            code, payload = 2, {"status": "ALREADY_RUNNING", "channels": []}
        else:
            recovered_at = datetime.now(timezone.utc)
            audit.recover_stale_runs(recovered_at - timedelta(hours=3), recovered_at)
            code, payload = orchestrate(
                channels=CHANNEL_NAMES, run_date=args.date, audit=audit, execute=_executor(args.config),
                sleep=time.sleep, retry_attempts=args.retry_attempts, retry_delay_seconds=args.retry_delay_seconds,
                max_workers=config.orchestrator_max_workers(len(CHANNEL_NAMES)), lock_already_acquired=True,
            )
    except Exception as error:
        code, payload = 2, {"status": "FAILED", "error_category": _category(error), "channels": []}
    finally:
        if audit is not None: audit.close()
    json.dump(payload, sys.stdout, ensure_ascii=False, separators=(",", ":"))
    sys.stdout.write("\n")
    return code


if __name__ == "__main__": raise SystemExit(main())
