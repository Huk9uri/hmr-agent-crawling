import json
from datetime import date
from pathlib import Path
from types import MappingProxyType
import unittest

import requests

from hmr_order_collection.channels.base import DateWindow, InvalidPeriodError
from hmr_order_collection.channels.lotteon import DELIVERY_ORDERS_URL, DELIVERY_PROGRESS_URL, LotteonAdapter
from hmr_order_collection.config import AppConfig
from hmr_order_collection.database import TABLES


FIXTURES = Path(__file__).with_name("fixtures")


def response(name, url):
    result = requests.Response()
    result.status_code = 200
    result.url = url
    result._content = (FIXTURES / name).read_bytes()
    return result


class FakeHttpClient:
    def __init__(self, fixtures_by_url):
        self.fixtures_by_url = fixtures_by_url
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return response(self.fixtures_by_url[url], url)


def config():
    return AppConfig(MappingProxyType({"LOTTEON_API_KEY": "SYNTHETIC_LOTTE_KEY"}))


class LotteonAdapterTests(unittest.TestCase):
    def test_explicit_invalid_period_response_raises_typed_probe_signal(self):
        adapter = LotteonAdapter(
            config(),
            http=FakeHttpClient(
                {
                    DELIVERY_ORDERS_URL: "lotteon_invalid_period.json",
                    DELIVERY_PROGRESS_URL: "lotteon_empty.json",
                }
            ),
        )

        with self.assertRaises(InvalidPeriodError):
            list(
                adapter.fetch(
                    DateWindow(date(2026, 8, 10), date(2026, 8, 10))
                )
            )
        self.assertEqual(adapter.pages_fetched, 1)

    def test_fetch_calls_only_two_read_only_search_endpoints_with_official_headers(self):
        http = FakeHttpClient({DELIVERY_ORDERS_URL: "lotteon_empty.json", DELIVERY_PROGRESS_URL: "lotteon_empty.json"})
        adapter = LotteonAdapter(config(), http=http)

        records = list(adapter.fetch(DateWindow(date(2026, 8, 10), date(2026, 8, 10))))

        self.assertEqual(records, [])
        self.assertEqual(adapter.pages_fetched, 2)
        self.assertEqual([call[0:2] for call in http.calls], [("POST", DELIVERY_ORDERS_URL), ("POST", DELIVERY_PROGRESS_URL)])
        for _, _, kwargs in http.calls:
            self.assertEqual(kwargs["headers"], {"Accept": "application/json", "Accept-Language": "ko", "Authorization": "Bearer SYNTHETIC_LOTTE_KEY", "Content-Type": "application/json", "X-Timezone": "GMT+09:00"})
            self.assertEqual(kwargs["json"], {"srchStrtDt": "20260810000000", "srchEndDt": "20260810235959"})

    def test_joins_delivery_progress_by_order_and_item_and_masks_raw_json(self):
        http = FakeHttpClient({DELIVERY_ORDERS_URL: "lotteon_delivery_orders.json", DELIVERY_PROGRESS_URL: "lotteon_delivery_progress.json"})

        record = next(LotteonAdapter(config(), http=http).fetch(DateWindow(date(2026, 8, 10), date(2026, 8, 10))))

        self.assertEqual(record.identity, ("LOTTE-ORDER-001", "3"))
        self.assertEqual(set(record.columns), set(TABLES["lotteon"].columns))
        self.assertEqual(record.columns["ProductId"], "LOTTE-PRODUCT-001")
        self.assertEqual(record.columns["DeliveryStatus"], "14")
        self.assertEqual(record.columns["DeliveryCompanyCode"], "0001")
        self.assertEqual(record.columns["TrackingNumber"], "SYNTHETIC-INVOICE-001")
        self.assertNotIn("SYNTHETIC_NAME_TO_MASK", record.raw_json)
        self.assertNotIn("SYNTHETIC_ORDERER_TO_MASK", record.raw_json)

    def test_rejects_the_documented_more_than_one_day_window_before_http(self):
        http = FakeHttpClient({})
        with self.assertRaisesRegex(ValueError, "1 day"):
            list(LotteonAdapter(config(), http=http).fetch(DateWindow(date(2026, 8, 9), date(2026, 8, 10))))
        self.assertEqual(http.calls, [])


if __name__ == "__main__":
    unittest.main()
