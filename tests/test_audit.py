from datetime import date, datetime, timezone
import unittest
from uuid import UUID

from hmr_order_collection.audit import ApplicationLock, AuditRepository


class Cursor:
    def __init__(self, lock_result=0, rowcount=0):
        self.lock_result = lock_result
        self.rowcount = rowcount
        self.calls = []
        self.closed = False
    def execute(self, sql, params=()):
        self.calls.append((sql, params))
    def fetchone(self):
        return (self.lock_result,)
    def close(self):
        self.closed = True


class Connection:
    def __init__(self, lock_result=0, rowcount=0):
        self.cursor_value = Cursor(lock_result, rowcount)
        self.commits = 0
        self.rollbacks = 0
        self.closed = False
    def cursor(self):
        return self.cursor_value
    def commit(self):
        self.commits += 1
    def rollback(self):
        self.rollbacks += 1
    def close(self):
        self.closed = True


class AuditRepositoryTests(unittest.TestCase):
    def test_application_lock_uses_exact_resource_and_releases_acquired_lock(self):
        connection = Connection(0)
        lock = ApplicationLock(connection)

        self.assertTrue(lock.acquire("HMR_ORDER_COLLECTION:naver"))
        lock.release("HMR_ORDER_COLLECTION:naver")

        self.assertEqual(connection.cursor_value.calls[0][1], ("HMR_ORDER_COLLECTION:naver",))
        self.assertIn("sp_releaseapplock", connection.cursor_value.calls[1][0])
        self.assertEqual(connection.cursor_value.calls[1][1], ("HMR_ORDER_COLLECTION:naver",))

    def test_application_lock_denial_returns_false_without_release(self):
        connection = Connection(-1)
        lock = ApplicationLock(connection)

        self.assertFalse(lock.acquire("HMR_ORDER_COLLECTION:ssg"))

        self.assertEqual(len(connection.cursor_value.calls), 1)

    def test_lock_result_controls_overlap(self):
        self.assertTrue(AuditRepository(Connection(0)).acquire_lock())
        self.assertFalse(AuditRepository(Connection(-1)).acquire_lock())

    def test_events_commit_independently_and_uuid_is_string(self):
        connection = Connection()
        repo = AuditRepository(connection)
        run_id = UUID("11111111-1111-1111-1111-111111111111")
        now = datetime(2026, 8, 12, tzinfo=timezone.utc)

        repo.start_run(run_id, date(2026, 8, 12), now)
        repo.record_attempt(run_id, "ssg", 1, now, now, "SUCCESS_EMPTY", {}, None)
        repo.finish_run(run_id, now, "SUCCESS", 7, 0)

        self.assertEqual(connection.commits, 3)
        self.assertTrue(all(str(run_id) in call[1] for call in connection.cursor_value.calls))

    def test_close_closes_connection(self):
        connection = Connection()
        AuditRepository(connection).close()
        self.assertTrue(connection.closed)

    def test_recover_stale_runs_commits_and_returns_updated_count(self):
        connection = Connection(rowcount=2)
        repo = AuditRepository(connection)
        cutoff = datetime(2026, 8, 21, 1, tzinfo=timezone.utc)
        recovered_at = datetime(2026, 8, 21, 4, tzinfo=timezone.utc)

        count = repo.recover_stale_runs(cutoff, recovered_at)

        self.assertEqual(count, 2)
        sql, params = connection.cursor_value.calls[-1]
        self.assertIn("RunStatus='ABORTED'", sql)
        self.assertEqual(params, (recovered_at, cutoff))
        self.assertEqual(connection.commits, 1)


if __name__ == "__main__":
    unittest.main()
