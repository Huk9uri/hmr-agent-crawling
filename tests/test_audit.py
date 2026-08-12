from datetime import date, datetime, timezone
import unittest
from uuid import UUID

from hmr_order_collection.audit import AuditRepository


class Cursor:
    def __init__(self, lock_result=0):
        self.lock_result = lock_result
        self.calls = []
        self.closed = False
    def execute(self, sql, params=()):
        self.calls.append((sql, params))
    def fetchone(self):
        return (self.lock_result,)
    def close(self):
        self.closed = True


class Connection:
    def __init__(self, lock_result=0):
        self.cursor_value = Cursor(lock_result)
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


if __name__ == "__main__":
    unittest.main()
