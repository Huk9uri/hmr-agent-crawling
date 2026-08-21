from datetime import date
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import threading
import unittest
from unittest.mock import patch

from hmr_order_collection.database import WriteSummary
from hmr_order_collection.orchestrator import _executor, main, orchestrate


class Audit:
    def __init__(self, locked=True):
        self.locked = locked
        self.attempts = []
        self.finished = None
    def acquire_lock(self): return self.locked
    def start_run(self, *args): self.started = args
    def record_attempt(self, *args): self.attempts.append(args)
    def finish_run(self, *args): self.finished = args


class OrchestratorTests(unittest.TestCase):
    def test_delayed_retry_does_not_block_a_ready_channel(self):
        calls = []
        sleeps = []
        outcomes = {
            "a": [RuntimeError(), {"records": 1, "inserted": 1}],
            "b": [{"records": 0}],
        }
        def execute(channel, run_date):
            calls.append((channel, run_date))
            value = outcomes[channel].pop(0)
            if isinstance(value, Exception): raise value
            return value

        audit = Audit()
        code, payload = orchestrate(
            channels=("a", "b"), run_date=date(2026, 8, 12), audit=audit,
            execute=execute, sleep=sleeps.append, retry_attempts=1, retry_delay_seconds=600,
            max_workers=1,
        )

        self.assertEqual(code, 0)
        self.assertEqual(payload["status"], "SUCCESS")
        self.assertEqual([item[0] for item in calls], ["a", "b", "a"])
        self.assertEqual(sleeps, [600])
        self.assertNotIn("error", str(payload).lower())

    def test_limits_peak_concurrency_and_preserves_input_order(self):
        channels = tuple(f"channel-{index}" for index in range(8))
        barrier = threading.Barrier(4)
        state_lock = threading.Lock()
        active = 0
        peak = 0

        def execute(channel, run_date):
            nonlocal active, peak
            with state_lock:
                active += 1
                peak = max(peak, active)
            barrier.wait(timeout=2)
            with state_lock:
                active -= 1
            return {"records": 0}

        code, payload = orchestrate(
            channels=channels, run_date=date(2026, 8, 12), audit=Audit(),
            execute=execute, sleep=lambda _: None, retry_attempts=0, max_workers=4,
        )

        self.assertEqual(code, 0)
        self.assertEqual(peak, 4)
        self.assertEqual([item["channel"] for item in payload["channels"]], list(channels))

    def test_final_failure_is_partial_and_does_not_block_later_channel(self):
        calls = []
        def execute(channel, run_date):
            calls.append(channel)
            if channel == "a": raise ValueError("secret response")
            return {"records": 0}

        audit = Audit()
        code, payload = orchestrate(
            channels=("a", "b"), run_date=date(2026, 8, 12), audit=audit,
            execute=execute, sleep=lambda _: None, retry_attempts=2, max_workers=2,
        )
        self.assertEqual(code, 1)
        self.assertEqual(payload["status"], "PARTIAL")
        self.assertEqual(calls.count("a"), 3)
        self.assertEqual(calls.count("b"), 1)
        self.assertEqual(payload["channels"][0]["status"], "FAILED_PARSE")
        self.assertEqual(payload["channels"][0]["attempts"], 3)
        self.assertEqual(payload["channels"][1]["status"], "SUCCESS_EMPTY")
        self.assertNotIn("secret", str(payload))
        self.assertNotIn("secret", str(audit.attempts))

    def test_rejects_invalid_scheduler_arguments(self):
        cases = (
            {"max_workers": 0},
            {"max_workers": 3},
            {"retry_attempts": -1},
            {"retry_delay_seconds": -1},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                arguments = dict(
                    channels=("a", "b"), run_date=date(2026, 8, 12), audit=Audit(),
                    execute=lambda *_: {"records": 0}, sleep=lambda _: None,
                    max_workers=2,
                )
                arguments.update(overrides)
                orchestrate(**arguments)

    def test_overlap_returns_nonzero_without_execution(self):
        code, payload = orchestrate(
            channels=("a",), run_date=date(2026, 8, 12), audit=Audit(False),
            execute=lambda *_: self.fail("must not execute"), sleep=lambda _: None,
            max_workers=1,
        )
        self.assertEqual(code, 2)
        self.assertEqual(payload, {"status": "ALREADY_RUNNING", "channels": []})


class AttemptExecutorTests(unittest.TestCase):
    class Cursor:
        def __init__(self, events, lock_result=0):
            self.events = events
            self.lock_result = lock_result

        def execute(self, sql, params=()):
            operation = "release" if "sp_releaseapplock" in sql else "acquire"
            self.events.append((operation, params))

        def fetchone(self):
            return (self.lock_result,)

        def close(self):
            pass

    class Connection:
        def __init__(self, events, lock_result=0):
            self.events = events
            self.cursor_value = AttemptExecutorTests.Cursor(events, lock_result)

        def cursor(self):
            return self.cursor_value

        def close(self):
            self.events.append(("close",))

    class Adapter:
        pages_fetched = 2

        def __init__(self, events, error=None):
            self.events = events
            self.error = error

        def fetch(self, window):
            self.events.append(("fetch", window))
            if self.error:
                raise self.error
            return ()

    class Writer:
        def __init__(self, events, error=None):
            self.events = events
            self.error = error

        def write(self, channel, records, run_id):
            self.events.append(("write", channel, tuple(records)))
            if self.error:
                raise self.error
            return WriteSummary()

    def build_executor(self, *, lock_result=0, adapter_error=None, writer_error=None):
        all_events = []
        connections = []

        def connect(_config):
            events = [("connect",)]
            all_events.append(events)
            connection = self.Connection(events, lock_result)
            connections.append(connection)
            return connection

        def registry(_config):
            return {"naver": self.Adapter(all_events[-1], adapter_error)}

        def writer(connection):
            return self.Writer(connection.events, writer_error)

        with patch("hmr_order_collection.orchestrator.load_config", return_value=object()):
            execute = _executor(
                Path("unused.env"), connection_factory=connect,
                registry_builder=registry, writer_factory=writer,
            )
        return execute, all_events, connections

    def test_each_attempt_uses_new_connection_and_holds_channel_lock_through_write(self):
        execute, all_events, connections = self.build_executor()

        execute("naver", date(2026, 8, 21))
        execute("naver", date(2026, 8, 21))

        self.assertEqual(len(connections), 2)
        for events in all_events:
            self.assertEqual([event[0] for event in events], ["connect", "acquire", "fetch", "write", "release", "close"])
            self.assertEqual(events[1][1], ("HMR_ORDER_COLLECTION:naver",))
            self.assertEqual(events[4][1], ("HMR_ORDER_COLLECTION:naver",))

    def test_attempt_releases_lock_and_closes_connection_on_fetch_or_write_failure(self):
        for failure_point in ("fetch", "write"):
            with self.subTest(failure_point=failure_point):
                options = {f"{failure_point}_error" if failure_point == "write" else "adapter_error": RuntimeError("secret")}
                if failure_point == "write":
                    options = {"writer_error": RuntimeError("secret")}
                execute, all_events, _ = self.build_executor(**options)
                with self.assertRaises(RuntimeError):
                    execute("naver", date(2026, 8, 21))
                event_names = [event[0] for event in all_events[0]]
                self.assertEqual(event_names[-2:], ["release", "close"])

    def test_lock_denial_skips_fetch_and_release_but_closes_connection(self):
        execute, all_events, _ = self.build_executor(lock_result=-1)

        with self.assertRaises(Exception) as raised:
            execute("naver", date(2026, 8, 21))

        self.assertEqual(raised.exception.__class__.__name__, "ChannelLockError")
        self.assertEqual([event[0] for event in all_events[0]], ["connect", "acquire", "close"])


class OrchestratorMainTests(unittest.TestCase):
    def test_main_recovers_stale_runs_and_passes_configured_worker_count(self):
        events = []

        class MainAudit:
            def acquire_lock(self):
                events.append(("acquire",))
                return True

            def recover_stale_runs(self, cutoff, recovered_at):
                events.append(("recover", cutoff, recovered_at))
                return 1

            def close(self):
                events.append(("close",))

        captured = {}

        def run(**kwargs):
            captured.update(kwargs)
            return 0, {"status": "SUCCESS", "channels": []}

        configured = type("Configured", (), {"orchestrator_max_workers": lambda self, count: 3})()
        stdout = StringIO()
        with (
            patch("hmr_order_collection.orchestrator.load_config", return_value=configured),
            patch("hmr_order_collection.orchestrator.connect_from_config", return_value=object()),
            patch("hmr_order_collection.orchestrator.AuditRepository", return_value=MainAudit()),
            patch("hmr_order_collection.orchestrator._executor", return_value=lambda *_: {}),
            patch("hmr_order_collection.orchestrator.orchestrate", side_effect=run),
            redirect_stdout(stdout),
        ):
            code = main(["--date", "2026-08-21", "--retry-delay-seconds", "0"])

        self.assertEqual(code, 0)
        self.assertEqual(captured["max_workers"], 3)
        self.assertEqual(events[1][0], "recover")
        self.assertEqual(events[1][2] - events[1][1], __import__("datetime").timedelta(hours=3))
        self.assertEqual(events[-1], ("close",))


if __name__ == "__main__": unittest.main()
