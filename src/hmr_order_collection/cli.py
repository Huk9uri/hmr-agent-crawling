"""Safe, count-only command line for read-only channel collection."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import date, timedelta
import json
from pathlib import Path
import sys
from typing import Any, TextIO
from uuid import uuid4

from hmr_order_collection.channels import (
    BOUNDARY_PROBE_START_DAYS,
    CHANNEL_NAMES,
    MAXIMUM_WINDOW_DAYS,
    build_adapter_registry,
)
from hmr_order_collection.channels.base import (
    ChannelAdapter,
    DateWindow,
    InvalidPeriodError,
    iter_windows,
)
from hmr_order_collection.config import AppConfig, ConfigurationError, load_config
from hmr_order_collection.database import DatabaseWriter, connect_from_config


class CliUsageError(ValueError):
    """A safe command-line validation failure with no credential content."""


class ChannelRunFailure(RuntimeError):
    """Carries a count-only partial summary while suppressing source details."""

    def __init__(self, summary: dict[str, Any]) -> None:
        super().__init__("channel execution failed")
        self.summary = summary


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CliUsageError("invalid command arguments")


def _parser() -> argparse.ArgumentParser:
    parser = _SafeArgumentParser(prog="python -m hmr_order_collection.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="list supported channel names")

    collect = commands.add_parser("collect", help="collect one channel")
    _add_collection_options(collect)
    collect.add_argument("--channel", required=True)
    collect.add_argument("--from", dest="start", required=True)

    collect_all = commands.add_parser("collect-all", help="collect every channel")
    _add_collection_options(collect_all)
    collect_all.add_argument("--maximum-window", action="store_true", required=True)
    collect_all.add_argument("--probe-boundaries", action="store_true")
    return parser


def _add_collection_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--to", dest="end", required=True)
    parser.add_argument("--config", type=Path, default=Path(".env"))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--write-db", action="store_true")
    parser.add_argument("--continue-on-error", action="store_true")


def _parse_date(raw_value: str) -> date:
    try:
        return date.fromisoformat(raw_value)
    except ValueError as error:
        raise CliUsageError("dates must use YYYY-MM-DD") from error


def _validate_dates(start: date, end: date, today: date) -> None:
    if start > end:
        raise CliUsageError("from date must not be after to date")
    if end > today:
        raise CliUsageError("dates cannot be in the future")


def _windows_for_channel(
    channel: str,
    *,
    start: date | None,
    end: date,
    maximum_window: bool,
) -> Iterable[DateWindow]:
    maximum_days = MAXIMUM_WINDOW_DAYS[channel]
    if maximum_window:
        start = end - timedelta(days=maximum_days - 1)
    if start is None:
        raise CliUsageError("from date is required")
    return iter_windows(start, end, maximum_days)


def _empty_summary(channel: str) -> dict[str, Any]:
    return {
        "channel": channel,
        "status": "ok",
        "windows": 0,
        "pages": 0,
        "records": 0,
        "inserted": 0,
        "changed": 0,
        "skipped": 0,
    }


def _fetch_windows(
    adapter: ChannelAdapter,
    windows: Iterable[DateWindow],
    summary: dict[str, Any],
) -> list[Any]:
    records: list[Any] = []
    for window in windows:
        window_records = list(adapter.fetch(window))
        records.extend(window_records)
        summary["windows"] += 1
        summary["records"] += len(window_records)
    return records


def _probe_boundary(
    channel: str,
    adapter: ChannelAdapter,
    end: date,
    summary: dict[str, Any],
) -> list[Any]:
    summary.update(probe_attempts=0, probe_invalid_periods=0)
    for candidate_days in range(BOUNDARY_PROBE_START_DAYS[channel], 0, -1):
        summary["probe_attempts"] += 1
        window = DateWindow(end - timedelta(days=candidate_days - 1), end)
        try:
            records = list(adapter.fetch(window))
        except InvalidPeriodError:
            summary["probe_invalid_periods"] += 1
            continue
        summary["verified_maximum_days"] = candidate_days
        summary["windows"] = 1
        summary["records"] = len(records)
        return records
    raise InvalidPeriodError("No accepted read-only period was found")


def _execute_channel(
    channel: str,
    adapter: ChannelAdapter,
    windows: Iterable[DateWindow],
    writer: DatabaseWriter | None,
    *,
    probe_boundary: bool,
    end: date,
) -> dict[str, Any]:
    summary = _empty_summary(channel)
    starting_pages = adapter.pages_fetched
    try:
        records = (
            _probe_boundary(channel, adapter, end, summary)
            if probe_boundary
            else _fetch_windows(adapter, windows, summary)
        )
        if writer is not None:
            written = writer.write(channel, records, uuid4())
            summary.update(
                inserted=written.inserted,
                changed=written.changed,
                skipped=written.skipped,
            )
    except Exception as error:
        summary.update(status="failed", error_type=type(error).__name__)
        raise ChannelRunFailure(summary) from None
    finally:
        summary["pages"] = adapter.pages_fetched - starting_pages
    return summary


def _render(payload: Mapping[str, Any], stream: TextIO) -> None:
    json.dump(payload, stream, ensure_ascii=False, separators=(",", ":"))
    stream.write("\n")


def main(
    argv: Sequence[str] | None = None,
    *,
    today: date | None = None,
    config_loader: Callable[[Path], AppConfig] = load_config,
    registry_builder: Callable[[AppConfig], Mapping[str, ChannelAdapter]] = build_adapter_registry,
    connection_factory: Callable[[AppConfig], Any] = connect_from_config,
    writer_factory: Callable[[Any], DatabaseWriter] = DatabaseWriter,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Run the CLI and return a process exit code without exposing record data."""
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    try:
        args = _parser().parse_args(argv)
        if args.command == "list":
            _render({"channels": list(CHANNEL_NAMES)}, stdout)
            return 0

        if args.command == "collect" and args.channel not in CHANNEL_NAMES:
            raise CliUsageError("unknown channel")

        end = _parse_date(args.end)
        start = _parse_date(args.start) if args.command == "collect" else None
        _validate_dates(start or end, end, today or date.today())
        if getattr(args, "probe_boundaries", False) and args.write_db:
            raise CliUsageError("boundary probing is dry-run only")
    except CliUsageError as error:
        stderr.write(f"error: {error}\n")
        return 2

    try:
        config = config_loader(args.config)
        adapters = dict(registry_builder(config))
    except ConfigurationError:
        stderr.write("error: invalid or incomplete configuration\n")
        return 2

    if args.command == "collect":
        channels = (args.channel,)
    else:
        channels = tuple(adapters)

    connection = None
    writer = None
    if args.write_db:
        try:
            connection = connection_factory(config)
            writer = writer_factory(connection)
        except Exception:
            stderr.write("error: database connection failed\n")
            return 2

    channel_summaries: list[dict[str, Any]] = []
    failure_count = 0
    close_failed = False
    try:
        for channel in channels:
            try:
                windows = _windows_for_channel(
                    channel,
                    start=start,
                    end=end,
                    maximum_window=args.command == "collect-all",
                )
                channel_summaries.append(
                    _execute_channel(
                        channel,
                        adapters[channel],
                        windows,
                        writer,
                        probe_boundary=(
                            getattr(args, "probe_boundaries", False)
                            and channel in BOUNDARY_PROBE_START_DAYS
                        ),
                        end=end,
                    )
                )
            except ChannelRunFailure as error:
                failure_count += 1
                channel_summaries.append(error.summary)
                if not args.continue_on_error:
                    break
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                close_failed = True
                stderr.write("error: database connection close failed\n")

    success_count = sum(item["status"] == "ok" for item in channel_summaries)
    status = (
        "failed"
        if close_failed
        else "ok"
        if not failure_count
        else "partial"
        if success_count
        else "failed"
    )
    payload = {
        "mode": "write-db" if args.write_db else "dry-run",
        "status": status,
        "channels": channel_summaries,
    }
    if close_failed:
        payload["database_close"] = "failed"
    _render(payload, stdout)
    return 1 if failure_count or close_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
