"""Behavior tests for the safe channel-collector command line."""

from __future__ import annotations

from datetime import date
from io import StringIO
import json
from types import MappingProxyType
import unittest

from hmr_order_collection.channels.base import DateWindow
from hmr_order_collection.config import AppConfig, ConfigurationError
from hmr_order_collection.database import WriteSummary


class FakeAdapter:
    def __init__(self, *, record_count=0, error=None):
        self.record_count = record_count
        self.error = error
        self.windows = []

    def fetch(self, window):
        self.windows.append(window)
        if self.error is not None:
            raise self.error
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
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def config(values=None):
    return AppConfig(MappingProxyType(dict(values or {})))


class CliTests(unittest.TestCase):
    def invoke(
        self,
        argv,
        *,
        adapters=None,
        writer=None,
        connection=None,
        connection_error=None,
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
            stdout=stdout,
            stderr=stderr,
        )
        output = json.loads(stdout.getvalue()) if stdout.getvalue() else None
        return code, output, stderr.getvalue(), calls, fake_writer, fake_connection

    def test_list_reports_all_channels_without_loading_secrets(self):
        code, output, error, calls, _writer, _connection = self.invoke(["list"])

        self.assertEqual(code, 0)
        self.assertEqual(
            output["channels"],
            ["naver", "coupang", "godomall", "lotteon", "elevenst", "ssg", "toss"],
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

    def test_dry_run_is_default_and_never_opens_a_database_connection(self):
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
            ],
            adapters={"naver": adapter},
        )

        self.assertEqual(code, 0)
        self.assertEqual(error, "")
        self.assertEqual(output["mode"], "dry-run")
        self.assertEqual(output["channels"][0]["records"], 2)
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
            "godomall": date(2026, 8, 10),
            "lotteon": date(2026, 8, 10),
            "elevenst": date(2026, 8, 10),
            "ssg": date(2026, 2, 12),
            "toss": date(2026, 7, 11),
        }
        for channel, adapter in adapters.items():
            self.assertEqual(MAXIMUM_WINDOW_DAYS[channel], (date(2026, 8, 10) - expected_starts[channel]).days + 1)
            self.assertEqual(adapter.windows, [DateWindow(expected_starts[channel], date(2026, 8, 10))])

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
    def test_registry_instantiates_all_seven_adapters_from_strict_config(self):
        from hmr_order_collection.channels import build_adapter_registry
        from hmr_order_collection.channels.coupang import CoupangAdapter
        from hmr_order_collection.channels.elevenst import ElevenstAdapter
        from hmr_order_collection.channels.godomall import GodomallAdapter
        from hmr_order_collection.channels.lotteon import LotteonAdapter
        from hmr_order_collection.channels.naver import NaverAdapter
        from hmr_order_collection.channels.ssg import SsgAdapter
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
