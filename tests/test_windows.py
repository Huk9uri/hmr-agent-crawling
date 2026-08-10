import unittest
from datetime import date

from hmr_order_collection.channels.base import iter_windows


class DateWindowTests(unittest.TestCase):
    def test_one_day_range_is_one_inclusive_window(self):
        self.assertEqual(
            [(window.start, window.end) for window in iter_windows(date(2026, 8, 10), date(2026, 8, 10), 1)],
            [(date(2026, 8, 10), date(2026, 8, 10))],
        )

    def test_twenty_four_day_range_does_not_drop_the_final_day(self):
        self.assertEqual(
            [(window.start, window.end) for window in iter_windows(date(2026, 1, 1), date(2026, 1, 24), 24)],
            [(date(2026, 1, 1), date(2026, 1, 24))],
        )

    def test_thirty_one_day_maximum_creates_adjacent_non_overlapping_windows(self):
        self.assertEqual(
            [(window.start, window.end) for window in iter_windows(date(2026, 1, 1), date(2026, 2, 1), 31)],
            [(date(2026, 1, 1), date(2026, 1, 31)), (date(2026, 2, 1), date(2026, 2, 1))],
        )

    def test_one_hundred_eighty_day_maximum_keeps_both_inclusive_endpoints(self):
        self.assertEqual(
            [(window.start, window.end) for window in iter_windows(date(2026, 1, 1), date(2026, 6, 30), 180)],
            [(date(2026, 1, 1), date(2026, 6, 29)), (date(2026, 6, 30), date(2026, 6, 30))],
        )

    def test_invalid_ranges_are_rejected(self):
        with self.assertRaises(ValueError):
            list(iter_windows(date(2026, 1, 2), date(2026, 1, 1), 1))
        with self.assertRaises(ValueError):
            list(iter_windows(date(2026, 1, 1), date(2026, 1, 1), 0))


if __name__ == "__main__":
    unittest.main()
