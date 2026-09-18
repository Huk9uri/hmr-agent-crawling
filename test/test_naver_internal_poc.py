import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from naver_internal_poc import summarize_dashboard


class NaverInternalPocTests(unittest.TestCase):
    def test_summarizes_only_safe_dashboard_counters(self):
        payload = {
            "newOrderCases": 2,
            "deliveryPreparingCases": 40,
            "deliveringCases": 255,
            "deliveredCases": 250,
            "purchaseCompleteCases": 438,
            "customerName": "do-not-log",
        }

        self.assertEqual(
            summarize_dashboard(payload),
            {
                "newOrderCases": 2,
                "deliveryPreparingCases": 40,
                "deliveringCases": 255,
                "deliveredCases": 250,
                "purchaseCompleteCases": 438,
            },
        )

    def test_rejects_non_mapping_dashboard_response(self):
        with self.assertRaisesRegex(TypeError, "dashboard response"):
            summarize_dashboard(None)


if __name__ == "__main__":
    unittest.main()
