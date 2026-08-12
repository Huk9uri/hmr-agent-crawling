from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]


class CollectionAuditSqlTests(unittest.TestCase):
    def test_migration_defines_idempotent_run_and_attempt_contract(self):
        sql = (ROOT / "sql/channel_orders/080_create_collection_audit_tables.sql").read_text(encoding="utf-8")

        for fragment in (
            "IF OBJECT_ID(N'dbo.CHANNEL_COLLECTION_RUN', N'U') IS NULL",
            "IF OBJECT_ID(N'dbo.CHANNEL_COLLECTION_ATTEMPT', N'U') IS NULL",
            "ScheduledDate date",
            "RunStatus nvarchar(30)",
            "ChannelName nvarchar(30)",
            "AttemptNo int",
            "RecordsCount int",
            "InsertedCount int",
            "ChangedCount int",
            "SkippedCount int",
            "ErrorCategory nvarchar(50)",
            "FOREIGN KEY (RunId)",
            "UNIQUE (RunId, ChannelName, AttemptNo)",
            "IX_CHANNEL_COLLECTION_RUN_SCHEDULED_STATUS",
            "IX_CHANNEL_COLLECTION_ATTEMPT_CHANNEL_STATUS",
        ):
            self.assertIn(fragment, sql)

    def test_verifier_checks_both_tables_and_indexes(self):
        sql = (ROOT / "sql/channel_orders/085_verify_collection_audit_tables.sql").read_text(encoding="utf-8")
        for fragment in (
            "CHANNEL_COLLECTION_RUN",
            "CHANNEL_COLLECTION_ATTEMPT",
            "IX_CHANNEL_COLLECTION_RUN_SCHEDULED_STATUS",
            "IX_CHANNEL_COLLECTION_ATTEMPT_CHANNEL_STATUS",
            "THROW",
        ):
            self.assertIn(fragment, sql)


if __name__ == "__main__":
    unittest.main()
