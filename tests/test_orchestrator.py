from datetime import date
import threading
import unittest

from hmr_order_collection.orchestrator import orchestrate


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


if __name__ == "__main__": unittest.main()
