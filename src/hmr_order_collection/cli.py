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
    CHANNEL_NAMES,
    MAXIMUM_WINDOW_DAYS,
    build_adapter_registry,
)
from hmr_order_collection.channels.base import ChannelAdapter, DateWindow, iter_windows
from hmr_order_collection.config import AppConfig, ConfigurationError, load_config
from hmr_order_collection.database import DatabaseWriter, connect_from_config


class CliUsageError(ValueError):
    """A safe command-line validation failure with no credential content."""


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
        "records": 0,
        "inserted": 0,
        "changed": 0,
        "skipped": 0,
    }


def _collect_channel(
    channel: str,
    adapter: ChannelAdapter,
    windows: Iterable[DateWindow],
    writer: DatabaseWriter | None,
) -> dict[str, Any]:
    summary = _empty_summary(channel)
    records: list[Any] = []
    for window in windows:
        window_records = list(adapter.fetch(window))
        records.extend(window_records)
        summary["windows"] += 1
        summary["records"] += len(window_records)
    if writer is not None:
        written = writer.write(channel, records, uuid4())
        summary.update(
            inserted=written.inserted,
            changed=written.changed,
            skipped=written.skipped,
        )
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
                    _collect_channel(channel, adapters[channel], windows, writer)
                )
            except Exception as error:
                failure_count += 1
                failed = _empty_summary(channel)
                failed.update(status="failed", error_type=type(error).__name__)
                channel_summaries.append(failed)
                if not args.continue_on_error:
                    break
    finally:
        if connection is not None:
            connection.close()

    success_count = sum(item["status"] == "ok" for item in channel_summaries)
    status = "ok" if not failure_count else ("partial" if success_count else "failed")
    _render(
        {
            "mode": "write-db" if args.write_db else "dry-run",
            "status": status,
            "channels": channel_summaries,
        },
        stdout,
    )
    return 1 if failure_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
