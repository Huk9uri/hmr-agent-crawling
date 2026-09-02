"""Behavior tests for the safe channel-collector command line."""

from __future__ import annotations

from datetime import date
from io import StringIO
import json
from types import MappingProxyType
import unittest

from hmr_order_collection.channels.base import ChannelAdapter, DateWindow, InvalidPeriodError
from hmr_order_collection.config import AppConfig, ConfigurationError
from hmr_order_collection.database import WriteSummary


class FakeAdapter(ChannelAdapter):
    def __init__(self, *, record_count=0, error=None, page_count=1):
        self.record_count = record_count
        self.error = error
        self.page_count = page_count
        self.windows = []

    def fetch(self, window):
        self.windows.append(window)
        for _ in range(self.page_count):
            self._record_page()
        if self.error is not None:
            raise self.error
        return iter([object()] * self.record_count)


class BoundaryAdapter(FakeAdapter):
    def __init__(self, maximum_accepted_days, *, record_count=0, error=None):
        super().__init__(record_count=record_count, error=error)
        self.maximum_accepted_days = maximum_accepted_days

    def fetch(self, window):
        self.windows.append(window)
        self._record_page()
        if self.error is not None:
            raise self.error
        inclusive_days = (window.end - window.start).days + 1
        if inclusive_days > self.maximum_accepted_days:
            raise InvalidPeriodError("synthetic invalid period detail must not be emitted")
        return iter([object()] * self.record_count)


class FakeWriter:
    def __init__(self, summary=WriteSummary(inserted=2, changed=1, skipped=3)):
        self.summary = summary
        self.calls = []

    def write(self, channel, records, run_id):
        records = tuple(records)
        self.calls.append((channel, records, run_id))
        return self.summary


class FakeConnection:
    def __init__(self, close_error=None):
        self.closed = False
        self.close_error = close_error

    def close(self):
        self.closed = True
        if self.close_error is not None:
            raise self.close_error


class PermissiveLock:
    def acquire(self, resource):
        return True

    def release(self, resource):
        pass


def config(values=None):
    return AppConfig(MappingProxyType(dict(values or {})))


class AppConfigTests(unittest.TestCase):
    def test_orchestrator_worker_count_defaults_to_four_and_accepts_channel_bound(self):
        self.assertEqual(config().orchestrator_max_workers(8), 4)
        for value in ("1", "4", "8"):
            with self.subTest(value=value):
                self.assertEqual(
                    config({"ORCHESTRATOR_MAX_WORKERS": value}).orchestrator_max_workers(8),
                    int(value),
                )

    def test_orchestrator_worker_count_rejects_invalid_values_without_echoing_them(self):
        for value in ("0", "9", "not-an-integer", ""):
            with self.subTest(value=value):
                with self.assertRaises(ConfigurationError) as raised:
                    config({"ORCHESTRATOR_MAX_WORKERS": value}).orchestrator_max_workers(8)
                self.assertNotIn(value or "<blank>", str(raised.exception))


class CliTests(unittest.TestCase):
    def invoke(
        self,
        argv,
        *,
        adapters=None,
        writer=None,
        connection=None,
        connection_error=None,
        lock_factory=None,
    ):
        from hmr_order_collection.cli import main

        stdout = StringIO()
        stderr = StringIO()
        calls = {"config": 0, "registry": 0, "connection": 0}
        adapter_values = adapters or {"naver": FakeAdapter()}
        fake_writer = writer or FakeWriter()
        fake_connection = connection or FakeConnection()

        def load(_path):
            calls["config"] += 1
            return config()

        def build(_config):
            calls["registry"] += 1
            return adapter_values

        def connect(_config):
            calls["connection"] += 1
            if connection_error is not None:
                raise connection_error
            return fake_connection

        code = main(
            argv,
            today=date(2026, 8, 10),
            config_loader=load,
            registry_builder=build,
            connection_factory=connect,
            writer_factory=lambda _connection: fake_writer,
            lock_factory=lock_factory or (lambda _connection: PermissiveLock()),
            stdout=stdout,
            stderr=stderr,
        )
        output = json.loads(stdout.getvalue()) if stdout.getvalue() else None
        return code, output, stderr.getvalue(), calls, fake_writer, fake_connection

    def test_write_mode_holds_channel_lock_around_channel_execution(self):
        events = []

        class EventAdapter(FakeAdapter):
            def fetch(self, window):
                events.append("fetch")
                return super().fetch(window)

        class EventWriter(FakeWriter):
            def write(self, channel, records, run_id):
                events.append("write")
                return super().write(channel, records, run_id)

        class EventLock:
            def acquire(self, resource):
                events.append(("acquire", resource))
                return True

            def release(self, resource):
                events.append(("release", resource))

        code, _output, _error, _calls, _writer, connection = self.invoke(
            ["collect", "--channel", "naver", "--from", "2026-08-10", "--to", "2026-08-10", "--write-db"],
            adapters={"naver": EventAdapter()}, writer=EventWriter(),
            lock_factory=lambda _connection: EventLock(),
        )

        self.assertEqual(code, 0)
        self.assertEqual(events, [
            ("acquire", "HMR_ORDER_COLLECTION:naver"), "fetch", "write",
            ("release", "HMR_ORDER_COLLECTION:naver"),
        ])
        self.assertTrue(connection.closed)

    def test_write_mode_releases_lock_when_writer_fails(self):
        events = []

        class FailingWriter(FakeWriter):
            def write(self, channel, records, run_id):
                raise RuntimeError("secret")

        class EventLock:
            def acquire(self, resource):
                events.append("acquire")
                return True

            def release(self, resource):
                events.append("release")

        code, output, _error, _calls, _writer, connection = self.invoke(
            ["collect", "--channel", "naver", "--from", "2026-08-10", "--to", "2026-08-10", "--write-db"],
            writer=FailingWriter(), lock_factory=lambda _connection: EventLock(),
        )

        self.assertEqual(code, 1)
        self.assertEqual(output["channels"][0]["status"], "failed")
        self.assertEqual(events, ["acquire", "release"])
        self.assertTrue(connection.closed)

    def test_write_mode_sanitizes_lock_release_failure_and_closes_connection(self):
        class FailingReleaseLock:
            def acquire(self, resource):
                return True

            def release(self, resource):
                raise RuntimeError("secret lock detail")

        code, output, error, _calls, _writer, connection = self.invoke(
            ["collect", "--channel", "naver", "--from", "2026-08-10", "--to", "2026-08-10", "--write-db"],
            lock_factory=lambda _connection: FailingReleaseLock(),
        )

        self.assertEqual(code, 1)
        self.assertEqual(error, "")
        self.assertEqual(output["channels"][0]["status"], "failed")
        self.assertNotIn("secret", json.dumps(output))
        self.assertTrue(connection.closed)

    def test_collect_all_stops_after_lock_release_failure(self):
        events = []

        class EventAdapter(FakeAdapter):
            def __init__(self, channel):
                super().__init__()
                self.channel = channel

            def fetch(self, window):
                events.append(("fetch", self.channel))
                return super().fetch(window)

        class FirstReleaseFails:
            def acquire(self, resource):
                events.append(("acquire", resource))
                return True

            def release(self, resource):
                events.append(("release", resource))
                raise RuntimeError("secret")

        code, output, _error, _calls, _writer, connection = self.invoke(
            ["collect-all", "--to", "2026-08-10", "--maximum-window", "--write-db"],
            adapters={"naver": EventAdapter("naver"), "coupang": EventAdapter("coupang")},
            lock_factory=lambda _connection: FirstReleaseFails(),
        )

        self.assertEqual(code, 1)
        self.assertEqual(len(output["channels"]), 1)
        self.assertEqual(events, [
            ("acquire", "HMR_ORDER_COLLECTION:naver"),
            ("fetch", "naver"),
            ("release", "HMR_ORDER_COLLECTION:naver"),
        ])
        self.assertTrue(connection.closed)

    def test_write_mode_lock_denial_skips_channel_and_dry_run_never_builds_lock(self):
        lock_calls = []

        class DeniedLock:
            def acquire(self, resource):
                lock_calls.append(("acquire", resource))
                return False

            def release(self, resource):
                lock_calls.append(("release", resource))

        write_code, write_output, _error, _calls, writer, _connection = self.invoke(
            ["collect", "--channel", "naver", "--from", "2026-08-10", "--to", "2026-08-10", "--write-db"],
            lock_factory=lambda _connection: DeniedLock(),
        )
        dry_code, _dry_output, _error, _calls, _writer, _connection = self.invoke(
            ["collect", "--channel", "naver", "--from", "2026-08-10", "--to", "2026-08-10"],
            lock_factory=lambda _connection: self.fail("dry-run must not create a lock"),
        )

        self.assertEqual(write_code, 1)
        self.assertEqual(write_output["channels"][0]["error_type"], "ChannelLockError")
        self.assertEqual(writer.calls, [])
        self.assertEqual(lock_calls, [("acquire", "HMR_ORDER_COLLECTION:naver")])
        self.assertEqual(dry_code, 0)

    def test_list_reports_all_channels_without_loading_secrets(self):
        code, output, error, calls, _writer, _connection = self.invoke(["list"])

        self.assertEqual(code, 0)
        self.assertEqual(
            output["channels"],
            ["naver", "coupang", "godomall", "lotteon", "elevenst", "ssg", "cj_onstyle", "toss"],
        )
        self.assertEqual(error, "")
        self.assertEqual(calls, {"config": 0, "registry": 0, "connection": 0})

    def test_unknown_channel_fails_before_configuration_is_loaded(self):
        code, output, error, calls, _writer, _connection = self.invoke(
            [
                "collect",
                "--channel",
                "unknown-shop",
                "--from",
                "2026-08-10",
                "--to",
                "2026-08-10",
            ]
        )

        self.assertEqual(code, 2)
        self.assertIsNone(output)
        self.assertIn("unknown channel", error.lower())
        self.assertNotIn("unknown-shop", error)
        self.assertEqual(calls, {"config": 0, "registry": 0, "connection": 0})

    def test_future_end_date_fails_before_any_adapter_or_database_is_created(self):
        code, output, error, calls, _writer, _connection = self.invoke(
            [
                "collect",
                "--channel",
                "naver",
                "--from",
                "2026-08-10",
                "--to",
                "2026-08-11",
            ]
        )

        self.assertEqual(code, 2)
        self.assertIsNone(output)
        self.assertIn("future", error.lower())
        self.assertEqual(calls, {"config": 0, "registry": 0, "connection": 0})

    def test_invalid_iso_date_is_rejected_with_sanitized_usage_error(self):
        code, output, error, calls, _writer, _connection = self.invoke(
            ["collect", "--channel", "naver", "--from", "not-a-date", "--to", "2026-08-10"]
        )

        self.assertEqual(code, 2)
        self.assertIsNone(output)
        self.assertEqual(error, "error: dates must use YYYY-MM-DD\n")
        self.assertNotIn("not-a-date", error)
        self.assertEqual(calls, {"config": 0, "registry": 0, "connection": 0})

    def test_from_after_to_is_rejected_before_configuration(self):
        code, output, error, calls, _writer, _connection = self.invoke(
            ["collect", "--channel", "naver", "--from", "2026-08-10", "--to", "2026-08-09"]
        )

        self.assertEqual(code, 2)
        self.assertIsNone(output)
        self.assertEqual(error, "error: from date must not be after to date\n")
        self.assertEqual(calls, {"config": 0, "registry": 0, "connection": 0})

    def test_dry_run_is_default_and_never_opens_a_database_connection(self):
        adapter = FakeAdapter(record_count=2, page_count=3)
        code, output, error, calls, writer, connection = self.invoke(
            [
                "collect",
                "--channel",
                "naver",
                "--from",
                "2026-08-10",
                "--to",
                "2026-08-10",
            ],
            adapters={"naver": adapter},
        )

        self.assertEqual(code, 0)
        self.assertEqual(error, "")
        self.assertEqual(output["mode"], "dry-run")
        self.assertEqual(output["channels"][0]["records"], 2)
        self.assertEqual(output["channels"][0]["pages"], 3)
        self.assertEqual(calls["connection"], 0)
        self.assertEqual(writer.calls, [])
        self.assertFalse(connection.closed)

    def test_write_db_is_the_only_flag_that_enables_persistence(self):
        adapter = FakeAdapter(record_count=2)
        code, output, error, calls, writer, connection = self.invoke(
            [
                "collect",
                "--channel",
                "naver",
                "--from",
                "2026-08-10",
                "--to",
                "2026-08-10",
                "--write-db",
            ],
            adapters={"naver": adapter},
        )

        self.assertEqual(code, 0)
        self.assertEqual(error, "")
        self.assertEqual(output["mode"], "write-db")
        self.assertEqual(output["channels"][0]["inserted"], 2)
        self.assertEqual(output["channels"][0]["changed"], 1)
        self.assertEqual(output["channels"][0]["skipped"], 3)
        self.assertEqual(calls["connection"], 1)
        self.assertEqual(len(writer.calls), 1)
        self.assertTrue(connection.closed)

    def test_database_connection_failure_is_reported_without_exception_details(self):
        code, output, error, calls, writer, connection = self.invoke(
            [
                "collect",
                "--channel",
                "naver",
                "--from",
                "2026-08-10",
                "--to",
                "2026-08-10",
                "--write-db",
            ],
            connection_error=RuntimeError("db.internal synthetic-password"),
        )

        self.assertEqual(code, 2)
        self.assertIsNone(output)
        self.assertEqual(error, "error: database connection failed\n")
        self.assertEqual(calls["connection"], 1)
        self.assertEqual(writer.calls, [])
        self.assertFalse(connection.closed)

    def test_database_close_failure_is_sanitized_and_preserves_channel_failure(self):
        connection = FakeConnection(
            close_error=RuntimeError("db.internal collector synthetic-password")
        )
        adapter = FakeAdapter(error=ValueError("primary secret-bearing failure"))
        code, output, error, _calls, _writer, returned_connection = self.invoke(
            [
                "collect",
                "--channel",
                "naver",
                "--from",
                "2026-08-10",
                "--to",
                "2026-08-10",
                "--write-db",
            ],
            adapters={"naver": adapter},
            connection=connection,
        )

        self.assertEqual(code, 1)
        self.assertEqual(error, "error: database connection close failed\n")
        self.assertEqual(output["status"], "failed")
        self.assertEqual(output["database_close"], "failed")
        self.assertEqual(output["channels"][0]["error_type"], "ValueError")
        rendered = json.dumps(output) + error
        self.assertNotIn("db.internal", rendered)
        self.assertNotIn("synthetic-password", rendered)
        self.assertNotIn("primary secret-bearing failure", rendered)
        self.assertTrue(returned_connection.closed)

    def test_maximum_window_ends_on_explicit_to_date_for_every_channel(self):
        from hmr_order_collection.channels import CHANNEL_NAMES, MAXIMUM_WINDOW_DAYS

        adapters = {name: FakeAdapter() for name in CHANNEL_NAMES}
        code, output, error, _calls, _writer, _connection = self.invoke(
            ["collect-all", "--to", "2026-08-10", "--maximum-window", "--dry-run"],
            adapters=adapters,
        )

        self.assertEqual(code, 0)
        self.assertEqual(error, "")
        self.assertEqual(output["status"], "ok")
        expected_starts = {
            "naver": date(2026, 8, 10),
            "coupang": date(2026, 7, 11),
            "godomall": date(2026, 7, 11),
            "lotteon": date(2026, 8, 10),
            "elevenst": date(2026, 7, 11),
            "ssg": date(2026, 2, 12),
            "cj_onstyle": date(2026, 7, 11),
            "toss": date(2026, 7, 11),
        }
        for channel, adapter in adapters.items():
            self.assertEqual(MAXIMUM_WINDOW_DAYS[channel], (date(2026, 8, 10) - expected_starts[channel]).days + 1)
            self.assertEqual(adapter.windows, [DateWindow(expected_starts[channel], date(2026, 8, 10))])

    def test_boundary_probe_reduces_only_explicit_invalid_periods_and_reports_safe_counts(self):
        adapter = BoundaryAdapter(maximum_accepted_days=28, record_count=2)
        code, output, error, calls, _writer, _connection = self.invoke(
            [
                "collect-all",
                "--to",
                "2026-08-10",
                "--maximum-window",
                "--probe-boundaries",
                "--dry-run",
            ],
            adapters={"godomall": adapter},
        )

        self.assertEqual(code, 0)
        self.assertEqual(error, "")
        summary = output["channels"][0]
        self.assertEqual(summary["probe_attempts"], 4)
        self.assertEqual(summary["probe_invalid_periods"], 3)
        self.assertEqual(summary["verified_maximum_days"], 28)
        self.assertEqual(summary["pages"], 4)
        self.assertEqual(summary["records"], 2)
        self.assertEqual(
            [(window.end - window.start).days + 1 for window in adapter.windows],
            [31, 30, 29, 28],
        )
        self.assertEqual(calls["connection"], 0)

    def test_boundary_probe_never_exceeds_lotteon_official_one_day_limit(self):
        adapter = BoundaryAdapter(maximum_accepted_days=1)
        code, output, error, _calls, _writer, _connection = self.invoke(
            [
                "collect-all",
                "--to",
                "2026-08-10",
                "--maximum-window",
                "--probe-boundaries",
            ],
            adapters={"lotteon": adapter},
        )

        self.assertEqual(code, 0)
        self.assertEqual(error, "")
        self.assertEqual(output["channels"][0]["verified_maximum_days"], 1)
        self.assertEqual(
            adapter.windows, [DateWindow(date(2026, 8, 10), date(2026, 8, 10))]
        )

    def test_boundary_probe_does_not_reduce_on_non_period_failure(self):
        adapter = BoundaryAdapter(
            maximum_accepted_days=28,
            error=RuntimeError("authentication failure detail"),
        )
        code, output, error, _calls, _writer, _connection = self.invoke(
            [
                "collect-all",
                "--to",
                "2026-08-10",
                "--maximum-window",
                "--probe-boundaries",
                "--continue-on-error",
            ],
            adapters={"godomall": adapter},
        )

        self.assertEqual(code, 1)
        self.assertEqual(error, "")
        self.assertEqual(len(adapter.windows), 1)
        self.assertEqual(output["channels"][0]["error_type"], "RuntimeError")

    def test_boundary_probe_is_rejected_in_write_mode(self):
        code, output, error, calls, _writer, _connection = self.invoke(
            [
                "collect-all",
                "--to",
                "2026-08-10",
                "--maximum-window",
                "--probe-boundaries",
                "--write-db",
            ]
        )

        self.assertEqual(code, 2)
        self.assertIsNone(output)
        self.assertEqual(error, "error: boundary probing is dry-run only\n")
        self.assertEqual(calls, {"config": 0, "registry": 0, "connection": 0})

    def test_reviewed_probe_result_drives_subsequent_write_window(self):
        probe_adapter = BoundaryAdapter(maximum_accepted_days=28, record_count=2)
        probe_code, probe_output, probe_error, _calls, _writer, _connection = self.invoke(
            [
                "collect-all",
                "--to",
                "2026-08-10",
                "--maximum-window",
                "--probe-boundaries",
            ],
            adapters={"godomall": probe_adapter},
        )
        verified_days = probe_output["channels"][0]["verified_maximum_days"]

        write_adapter = BoundaryAdapter(maximum_accepted_days=28, record_count=2)
        write_code, write_output, write_error, calls, writer, connection = self.invoke(
            [
                "collect-all",
                "--to",
                "2026-08-10",
                "--maximum-window",
                "--verified-maximum-days",
                f"godomall={verified_days}",
                "--write-db",
            ],
            adapters={"godomall": write_adapter},
        )

        self.assertEqual((probe_code, probe_error), (0, ""))
        self.assertEqual((write_code, write_error), (0, ""))
        self.assertEqual(write_output["channels"][0]["applied_verified_maximum_days"], 28)
        self.assertEqual(
            write_adapter.windows,
            [DateWindow(date(2026, 7, 14), date(2026, 8, 10))],
        )
        self.assertEqual(len(writer.calls), 1)
        self.assertEqual(calls["connection"], 1)
        self.assertTrue(connection.closed)

    def test_verified_maximum_days_accepts_repeatable_reviewed_channel_values(self):
        adapters = {
            "godomall": BoundaryAdapter(maximum_accepted_days=31),
            "elevenst": BoundaryAdapter(maximum_accepted_days=31),
        }
        code, output, error, _calls, _writer, _connection = self.invoke(
            [
                "collect-all",
                "--to",
                "2026-08-10",
                "--maximum-window",
                "--verified-maximum-days",
                "godomall=31",
                "--verified-maximum-days",
                "elevenst=31",
            ],
            adapters=adapters,
        )

        self.assertEqual(code, 0)
        self.assertEqual(error, "")
        self.assertEqual(
            [item["applied_verified_maximum_days"] for item in output["channels"]],
            [31, 31],
        )

    def test_verified_maximum_days_rejects_unknown_fixed_duplicate_and_invalid_values(self):
        cases = (
            ["--verified-maximum-days", "unknown=1"],
            ["--verified-maximum-days", "lotteon=1"],
            ["--verified-maximum-days", "godomall=0"],
            ["--verified-maximum-days", "godomall=32"],
            ["--verified-maximum-days", "elevenst=32"],
            ["--verified-maximum-days", "godomall=not-an-integer"],
            [
                "--verified-maximum-days",
                "godomall=28",
                "--verified-maximum-days",
                "godomall=27",
            ],
        )
        for options in cases:
            with self.subTest(options=options):
                code, output, error, calls, _writer, _connection = self.invoke(
                    [
                        "collect-all",
                        "--to",
                        "2026-08-10",
                        "--maximum-window",
                        *options,
                    ]
                )
                self.assertEqual(code, 2)
                self.assertIsNone(output)
                self.assertEqual(error, "error: invalid verified maximum days\n")
                self.assertEqual(
                    calls, {"config": 0, "registry": 0, "connection": 0}
                )

    def test_verified_maximum_days_requires_maximum_window(self):
        code, output, error, calls, _writer, _connection = self.invoke(
            [
                "collect-all",
                "--to",
                "2026-08-10",
                "--verified-maximum-days",
                "godomall=28",
            ]
        )

        self.assertEqual(code, 2)
        self.assertIsNone(output)
        self.assertEqual(error, "error: invalid command arguments\n")
        self.assertEqual(calls, {"config": 0, "registry": 0, "connection": 0})

    def test_continue_on_error_isolates_failures_and_summary_never_leaks_error_values(self):
        adapters = {
            "naver": FakeAdapter(error=RuntimeError("SECRET_TOKEN Alice 010-1234-5678")),
            "coupang": FakeAdapter(record_count=4),
        }
        code, output, error, _calls, _writer, _connection = self.invoke(
            [
                "collect-all",
                "--to",
                "2026-08-10",
                "--maximum-window",
                "--dry-run",
                "--continue-on-error",
            ],
            adapters=adapters,
        )

        self.assertEqual(code, 1)
        self.assertEqual(error, "")
        self.assertEqual(output["status"], "partial")
        self.assertEqual(output["channels"][0], {
            "channel": "naver",
            "status": "failed",
            "windows": 0,
            "pages": 1,
            "records": 0,
            "inserted": 0,
            "changed": 0,
            "skipped": 0,
            "error_type": "RuntimeError",
        })
        self.assertEqual(output["channels"][1]["status"], "ok")
        self.assertEqual(output["channels"][1]["records"], 4)
        rendered = json.dumps(output)
        self.assertNotIn("SECRET_TOKEN", rendered)
        self.assertNotIn("Alice", rendered)
        self.assertNotIn("010-1234-5678", rendered)
        self.assertEqual(adapters["coupang"].windows, [DateWindow(date(2026, 7, 11), date(2026, 8, 10))])

    def test_without_continue_on_error_later_channels_are_not_called(self):
        adapters = {
            "naver": FakeAdapter(error=RuntimeError("synthetic failure")),
            "coupang": FakeAdapter(record_count=4),
        }
        code, output, error, _calls, _writer, _connection = self.invoke(
            ["collect-all", "--to", "2026-08-10", "--maximum-window"],
            adapters=adapters,
        )

        self.assertEqual(code, 1)
        self.assertEqual(error, "")
        self.assertEqual(output["status"], "failed")
        self.assertEqual(len(output["channels"]), 1)
        self.assertEqual(adapters["coupang"].windows, [])


class AdapterRegistryTests(unittest.TestCase):
    def test_registry_instantiates_all_eight_adapters_from_strict_config(self):
        from hmr_order_collection.channels import build_adapter_registry
        from hmr_order_collection.channels.coupang import CoupangAdapter
        from hmr_order_collection.channels.elevenst import ElevenstAdapter
        from hmr_order_collection.channels.godomall import GodomallAdapter
        from hmr_order_collection.channels.lotteon import LotteonAdapter
        from hmr_order_collection.channels.naver import NaverAdapter
        from hmr_order_collection.channels.ssg import SsgAdapter
        from hmr_order_collection.channels.cj_onstyle import CjOnstyleAdapter
        from hmr_order_collection.channels.toss import TossShoppingAdapter

        values = {
            "NAVER_COMMERCE_CLIENT_ID": "synthetic",
            "NAVER_COMMERCE_CLIENT_SECRET": "$2b$04$abcdefghijklmnopqrstuu",
            "COUPANG_VENDOR_ID": "synthetic",
            "COUPANG_ACCESS_KEY": "synthetic",
            "COUPANG_SECRET_KEY": "synthetic",
            "GODOMALL_PARTNER_KEY": "synthetic",
            "GODOMALL_USER_KEY": "synthetic",
            "LOTTEON_API_KEY": "synthetic",
            "ELEVENST_API_KEY": "synthetic",
            "SSG_API_KEY": "synthetic",
            "CJ_ONSTYLE_VENDOR_CODE": "synthetic",
            "CJ_ONSTYLE_AUTHENTICATION_KEY": "synthetic",
            "TOSS_SHOPPING_ACCESS_KEY": "synthetic",
            "TOSS_SHOPPING_SECRET_KEY": "synthetic",
        }
        registry = build_adapter_registry(config(values))

        self.assertEqual(
            {name: type(adapter) for name, adapter in registry.items()},
            {
                "naver": NaverAdapter,
                "coupang": CoupangAdapter,
                "godomall": GodomallAdapter,
                "lotteon": LotteonAdapter,
                "elevenst": ElevenstAdapter,
                "ssg": SsgAdapter,
                "cj_onstyle": CjOnstyleAdapter,
                "toss": TossShoppingAdapter,
            },
        )

    def test_registry_rejects_partial_credentials_instead_of_skipping_channels(self):
        from hmr_order_collection.channels import build_adapter_registry

        with self.assertRaises(ConfigurationError):
            build_adapter_registry(config({"NAVER_COMMERCE_CLIENT_ID": "synthetic"}))


class DatabaseConnectionFactoryTests(unittest.TestCase):
    def test_connection_uses_only_strict_config_values_and_integer_port(self):
        from hmr_order_collection.database import connect_from_config

        calls = []

        def connector(**kwargs):
            calls.append(kwargs)
            return "connection"

        result = connect_from_config(
            config(
                {
                    "DB_SERVER": "db.internal",
                    "DB_NAME": "ecommerce",
                    "DB_USER": "collector",
                    "DB_PASSWORD": "synthetic-password",
                    "DB_PORT": "14330",
                }
            ),
            connector=connector,
        )

        self.assertEqual(result, "connection")
        self.assertEqual(calls, [{
            "server": "db.internal",
            "database": "ecommerce",
            "user": "collector",
            "password": "synthetic-password",
            "port": 14330,
            "login_timeout": 10,
            "timeout": 60,
        }])

    def test_connection_rejects_invalid_port_before_calling_driver(self):
        from hmr_order_collection.database import connect_from_config

        calls = []
        with self.assertRaises(ConfigurationError):
            connect_from_config(
                config(
                    {
                        "DB_SERVER": "db.internal",
                        "DB_NAME": "ecommerce",
                        "DB_USER": "collector",
                        "DB_PASSWORD": "synthetic-password",
                        "DB_PORT": "not-a-port",
                    }
                ),
                connector=lambda **kwargs: calls.append(kwargs),
            )
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
