"""Daily, channel-isolated order collection orchestration."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Iterable
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import time
from typing import Any
from uuid import uuid4

from hmr_order_collection.audit import AuditRepository
from hmr_order_collection.channels import CHANNEL_NAMES, MAXIMUM_WINDOW_DAYS, build_adapter_registry
from hmr_order_collection.channels.base import DateWindow
from hmr_order_collection.config import ConfigurationError, load_config
from hmr_order_collection.database import DatabaseWriter, connect_from_config
from hmr_order_collection.http import HttpResponseError


def _category(error: Exception) -> str:
    if isinstance(error, ConfigurationError): return "FAILED_CONFIG"
    if isinstance(error, HttpResponseError): return "FAILED_API"
    if isinstance(error, (ValueError, TypeError, KeyError)): return "FAILED_PARSE"
    if error.__class__.__module__.startswith("pymssql"): return "FAILED_DB"
    return "FAILED_INTERNAL"


def orchestrate(*, channels: Iterable[str], run_date: date, audit: Any,
                execute: Callable[[str, date], dict[str, int]], sleep: Callable[[float], None],
                retry_attempts: int = 2, retry_delay_seconds: int = 600) -> tuple[int, dict[str, Any]]:
    if not audit.acquire_lock():
        return 2, {"status": "ALREADY_RUNNING", "channels": []}
    run_id = uuid4()
    audit.start_run(run_id, run_date, datetime.now(timezone.utc))
    results = []
    for channel in channels:
        final = None
        for attempt in range(1, retry_attempts + 2):
            started = datetime.now(timezone.utc)
            try:
                counts = execute(channel, run_date)
                status = "SUCCESS_WITH_DATA" if counts.get("records", 0) else "SUCCESS_EMPTY"
                category = None
            except Exception as error:
                counts = {}
                status = category = _category(error)
            finished = datetime.now(timezone.utc)
            audit.record_attempt(run_id, channel, attempt, started, finished, status, counts, category)
            final = {"channel": channel, "status": status, "attempts": attempt,
                     **{key: counts.get(key, 0) for key in ("windows", "pages", "records", "inserted", "changed", "skipped")}}
            if status.startswith("SUCCESS_"): break
            if attempt <= retry_attempts: sleep(retry_delay_seconds)
        results.append(final)
    successful = sum(item["status"].startswith("SUCCESS_") for item in results)
    failed = len(results) - successful
    status = "SUCCESS" if not failed else "PARTIAL" if successful else "FAILED"
    audit.finish_run(run_id, datetime.now(timezone.utc), status, successful, failed)
    return (0 if not failed else 1), {"status": status, "channels": results}


def _executor(config_path: Path) -> Callable[[str, date], dict[str, int]]:
    config = load_config(config_path)
    def execute(channel: str, run_date: date) -> dict[str, int]:
        adapter = build_adapter_registry(config)[channel]
        start = run_date - timedelta(days=MAXIMUM_WINDOW_DAYS[channel] - 1)
        records = list(adapter.fetch(DateWindow(start, run_date)))
        connection = connect_from_config(config)
        try:
            written = DatabaseWriter(connection).write(channel, records, uuid4())
        finally:
            connection.close()
        return {"windows": 1, "pages": adapter.pages_fetched, "records": len(records),
                "inserted": written.inserted, "changed": written.changed, "skipped": written.skipped}
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
        code, payload = orchestrate(
            channels=CHANNEL_NAMES, run_date=args.date, audit=audit, execute=_executor(args.config),
            sleep=time.sleep, retry_attempts=args.retry_attempts, retry_delay_seconds=args.retry_delay_seconds,
        )
    except Exception as error:
        code, payload = 2, {"status": "FAILED", "error_category": _category(error), "channels": []}
    finally:
        if audit is not None: audit.close()
    json.dump(payload, sys.stdout, ensure_ascii=False, separators=(",", ":"))
    sys.stdout.write("\n")
    return code


if __name__ == "__main__": raise SystemExit(main())
