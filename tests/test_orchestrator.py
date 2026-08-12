from datetime import date
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
    def test_retries_failure_twice_then_succeeds_and_continues(self):
        calls = []
        sleeps = []
        outcomes = {
            "a": [RuntimeError(), RuntimeError(), {"records": 1, "inserted": 1}],
            "b": [{"records": 0}],
        }
        def execute(channel, run_date):
            calls.append((channel, run_date))
            value = outcomes[channel].pop(0)
            if isinstance(value, Exception): raise value
            return value

        code, payload = orchestrate(
            channels=("a", "b"), run_date=date(2026, 8, 12), audit=Audit(),
            execute=execute, sleep=sleeps.append, retry_attempts=2, retry_delay_seconds=600,
        )

        self.assertEqual(code, 0)
        self.assertEqual(payload["status"], "SUCCESS")
        self.assertEqual([item[0] for item in calls], ["a", "a", "a", "b"])
        self.assertEqual(sleeps, [600, 600])
        self.assertNotIn("error", str(payload).lower())

    def test_final_failure_is_partial_and_does_not_block_later_channel(self):
        calls = []
        def execute(channel, run_date):
            calls.append(channel)
            if channel == "a": raise ValueError("secret response")
            return {"records": 0}

        code, payload = orchestrate(
            channels=("a", "b"), run_date=date(2026, 8, 12), audit=Audit(),
            execute=execute, sleep=lambda _: None, retry_attempts=0,
        )
        self.assertEqual(code, 1)
        self.assertEqual(payload["status"], "PARTIAL")
        self.assertEqual(calls, ["a", "b"])
        self.assertEqual(payload["channels"][0]["status"], "FAILED_PARSE")
        self.assertEqual(payload["channels"][1]["status"], "SUCCESS_EMPTY")
        self.assertNotIn("secret", str(payload))

    def test_overlap_returns_nonzero_without_execution(self):
        code, payload = orchestrate(
            channels=("a",), run_date=date(2026, 8, 12), audit=Audit(False),
            execute=lambda *_: self.fail("must not execute"), sleep=lambda _: None,
        )
        self.assertEqual(code, 2)
        self.assertEqual(payload, {"status": "ALREADY_RUNNING", "channels": []})


if __name__ == "__main__": unittest.main()
