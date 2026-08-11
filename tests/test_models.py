import unittest

from hmr_order_collection.models import ChannelRecord


class ChannelRecordTests(unittest.TestCase):
    def test_columns_cannot_be_mutated_after_record_construction(self):
        record = ChannelRecord(
            identity=("ORDER-1",),
            columns={"status": "PAID"},
            raw_json="{}",
            payload_hash=b"x" * 32,
        )

        with self.assertRaises(TypeError):
            record.columns["status"] = "CANCELLED"


if __name__ == "__main__":
    unittest.main()
