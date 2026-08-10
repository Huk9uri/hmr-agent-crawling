import copy
import unittest
from datetime import datetime, timezone
from uuid import UUID

from hmr_order_collection.database import DatabaseWriter
from hmr_order_collection.models import ChannelRecord


class InMemoryHistoryConnection:
    """A small SQL Server boundary fake which applies the writer's SQL effects."""

    def __init__(self, rows=(), fail_on_insert=None):
        self.rows = copy.deepcopy(list(rows))
        self._pending = None
        self.executed = []
        self.commit_count = 0
        self.rollback_count = 0
        self.fail_on_insert = fail_on_insert
        self.insert_attempts = 0

    def cursor(self):
        self._pending = copy.deepcopy(self.rows)
        return InMemoryHistoryCursor(self)

    def commit(self):
        self.rows = self._pending
        self.commit_count += 1
        self._pending = None

    def rollback(self):
        self.rollback_count += 1
        self._pending = None


class InMemoryHistoryCursor:
    def __init__(self, connection):
        self.connection = connection
        self._last_row = None

    def execute(self, sql, parameters=()):
        self.connection.executed.append((sql, tuple(parameters)))
        if sql.startswith("SELECT PayloadHash"):
            identity = tuple(parameters)
            row = next((row for row in self.connection._pending if row["identity"] == identity and row["is_latest"]), None)
            self._last_row = None if row is None else (row["payload_hash"],)
        elif sql.startswith("UPDATE"):
            identity = tuple(parameters)
            for row in self.connection._pending:
                if row["identity"] == identity and row["is_latest"]:
                    row["is_latest"] = False
        elif sql.startswith("INSERT"):
            self.connection.insert_attempts += 1
            if self.connection.fail_on_insert == self.connection.insert_attempts:
                raise RuntimeError("simulated insert failure")
            identity = tuple(parameters[2:4])
            self.connection._pending.append(
                {"identity": identity, "payload_hash": parameters[-2], "is_latest": bool(parameters[-1])}
            )

    def fetchone(self):
        return self._last_row

    def close(self):
        pass


def record(order_no="ORDER-1", item_sno="ITEM-1", payload_hash=b"a" * 32, **columns):
    return ChannelRecord(
        identity=(order_no, item_sno),
        columns={"OrderNo": order_no, "OrderItemSno": item_sno, "ProductName": "Synthetic order", **columns},
        raw_json='{"masked": true}',
        payload_hash=payload_hash,
    )


class DatabaseWriterTests(unittest.TestCase):
    run_id = UUID("12345678-1234-5678-1234-567812345678")

    def writer(self, connection):
        return DatabaseWriter(connection, now=lambda: datetime(2026, 8, 10, 12, tzinfo=timezone.utc))

    def test_new_payload_inserts_a_latest_history_row(self):
        connection = InMemoryHistoryConnection()

        summary = self.writer(connection).write("godomall", [record()], self.run_id)

        self.assertEqual((summary.inserted, summary.changed, summary.skipped), (1, 0, 0))
        self.assertEqual([(row["identity"], row["is_latest"]) for row in connection.rows], [(("ORDER-1", "ITEM-1"), True)])
        self.assertEqual(connection.commit_count, 1)
        self.assertIn("SET ANSI_NULLS ON", [sql for sql, _ in connection.executed])

    def test_unchanged_payload_skips_history_insert(self):
        connection = InMemoryHistoryConnection(
            [{"identity": ("ORDER-1", "ITEM-1"), "payload_hash": b"a" * 32, "is_latest": True}]
        )

        summary = self.writer(connection).write("godomall", [record()], self.run_id)

        self.assertEqual((summary.inserted, summary.changed, summary.skipped), (0, 0, 1))
        self.assertEqual(len(connection.rows), 1)
        self.assertEqual(connection.commit_count, 1)

    def test_changed_payload_replaces_the_latest_history_row(self):
        connection = InMemoryHistoryConnection(
            [{"identity": ("ORDER-1", "ITEM-1"), "payload_hash": b"a" * 32, "is_latest": True}]
        )

        summary = self.writer(connection).write("godomall", [record(payload_hash=b"b" * 32)], self.run_id)

        self.assertEqual((summary.inserted, summary.changed, summary.skipped), (1, 1, 0))
        self.assertEqual([row["is_latest"] for row in connection.rows], [False, True])
        select_sql = next(sql for sql, _ in connection.executed if sql.startswith("SELECT PayloadHash"))
        self.assertIn("WITH (UPDLOCK, HOLDLOCK)", select_sql)

    def test_any_row_failure_rolls_back_the_entire_transaction(self):
        original = [{"identity": ("EXISTING", "ITEM-0"), "payload_hash": b"z" * 32, "is_latest": True}]
        connection = InMemoryHistoryConnection(original, fail_on_insert=2)

        with self.assertRaisesRegex(RuntimeError, "simulated insert failure"):
            self.writer(connection).write("godomall", [record("ORDER-1"), record("ORDER-2")], self.run_id)

        self.assertEqual(connection.rows, original)
        self.assertEqual(connection.rollback_count, 1)
        self.assertEqual(connection.commit_count, 0)

    def test_api_supplied_identifier_is_rejected_before_any_sql_is_executed(self):
        connection = InMemoryHistoryConnection()
        malicious = record(**{"OrderNo]; DROP TABLE dbo.GODOMALL_ORDER_ITEM;--": "x"})

        with self.assertRaises(ValueError):
            self.writer(connection).write("godomall", [malicious], self.run_id)

        self.assertEqual(connection.executed, [])


if __name__ == "__main__":
    unittest.main()
