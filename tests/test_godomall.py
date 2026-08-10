from datetime import date
from pathlib import Path
from types import MappingProxyType
import unittest

import requests

from hmr_order_collection.channels.base import DateWindow, InvalidPeriodError
from hmr_order_collection.channels.godomall import GODOMALL_ORDER_SEARCH_URL, GodomallAdapter
from hmr_order_collection.config import AppConfig
from hmr_order_collection.database import TABLES


FIXTURES = Path(__file__).with_name("fixtures")


def xml_response(name, url="https://synthetic.invalid"):
    result = requests.Response()
    result.status_code = 200
    result.url = url
    result._content = (FIXTURES / name).read_bytes()
    return result


class FakeHttpClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return xml_response(next(self.responses), url)


def config():
    return AppConfig(MappingProxyType({"GODOMALL_PARTNER_KEY": "SYNTHETIC_PARTNER", "GODOMALL_USER_KEY": "SYNTHETIC_USER"}))


class GodomallAdapterTests(unittest.TestCase):
    def test_explicit_invalid_period_response_raises_typed_probe_signal(self):
        adapter = GodomallAdapter(
            config(), http=FakeHttpClient(["godomall_invalid_period.xml"])
        )

        with self.assertRaises(InvalidPeriodError):
            list(
                adapter.fetch(
                    DateWindow(date(2026, 7, 11), date(2026, 8, 10))
                )
            )
        self.assertEqual(adapter.pages_fetched, 1)

    def test_fetch_follows_last_order_to_a_normal_final_page(self):
        http = FakeHttpClient(["godomall_orders_page.xml", "godomall_orders_last_page.xml"])
        adapter = GodomallAdapter(config(), http=http)

        records = list(adapter.fetch(DateWindow(date(2026, 8, 10), date(2026, 8, 10))))

        self.assertEqual(len(records), 3)
        self.assertEqual(adapter.pages_fetched, 2)
        self.assertEqual(len(http.calls), 2)
        self.assertEqual(http.calls[0][0:2], ("POST", GODOMALL_ORDER_SEARCH_URL))
        self.assertEqual(http.calls[0][2]["data"], {"partner_key": "SYNTHETIC_PARTNER", "key": "SYNTHETIC_USER", "dateType": "order", "startDate": "2026-08-10", "endDate": "2026-08-10", "size": 100})
        self.assertEqual(http.calls[1][2]["data"]["lastOrder"], "GODO-ORDER-001")

    def test_fetch_raises_when_more_pages_have_a_repeated_continuation(self):
        http = FakeHttpClient(["godomall_orders_page.xml", "godomall_orders_page.xml"])

        with self.assertRaisesRegex(ValueError, "continuation"):
            list(GodomallAdapter(config(), http=http).fetch(DateWindow(date(2026, 8, 10), date(2026, 8, 10))))

    def test_fetch_raises_when_more_pages_have_no_continuation(self):
        http = FakeHttpClient(["godomall_missing_cursor_page.xml"])

        with self.assertRaisesRegex(ValueError, "continuation"):
            list(GodomallAdapter(config(), http=http).fetch(DateWindow(date(2026, 8, 10), date(2026, 8, 10))))

    def test_maps_only_deployed_columns_retains_channel_and_masks_raw_xml(self):
        http = FakeHttpClient(["godomall_orders_page.xml", "godomall_empty_page.xml"])

        record = next(GodomallAdapter(config(), http=http).fetch(DateWindow(date(2026, 8, 10), date(2026, 8, 10))))

        self.assertEqual(record.identity, ("GODO-ORDER-002", "GODO-ITEM-002-A"))
        self.assertEqual(set(record.columns), set(TABLES["godomall"].columns))
        self.assertEqual(record.columns["OrderChannelCode"], "naverpay")
        self.assertEqual(record.columns["ExternalOrderNo"], "GODO-EXTERNAL-002")
        self.assertEqual(record.columns["ProductCode"], "GODO-PRODUCT-002")
        self.assertEqual(record.columns["Quantity"], 2)
        self.assertEqual(record.columns["PaidAt"], "2026-08-10 11:01:00")
        self.assertEqual(record.columns["DispatchedAt"], "2026-08-10 18:00:00")
        self.assertNotIn("SYNTHETIC_NAME_TO_MASK", record.raw_json)
        self.assertNotIn("synthetic@example.invalid", record.raw_json)
        self.assertNotIn("SYNTHETIC_ADDRESS_TO_MASK", record.raw_json)
        self.assertNotIn("SYNTHETIC_SAFE_NUMBER_TO_MASK", record.raw_json)

    def test_zero_datetime_sentinels_are_normalized_to_none(self):
        record = next(
            GodomallAdapter(
                config(), http=FakeHttpClient(["godomall_zero_dates.xml"])
            ).fetch(DateWindow(date(2026, 8, 10), date(2026, 8, 10)))
        )

        self.assertEqual(record.columns["OrderedAt"], "2026-08-10 10:00:00")
        self.assertIsNone(record.columns["PaidAt"])
        self.assertIsNone(record.columns["DispatchedAt"])

    def test_successful_empty_response_returns_zero_records(self):
        http = FakeHttpClient(["godomall_empty_page.xml"])
        self.assertEqual(list(GodomallAdapter(config(), http=http).fetch(DateWindow(date(2026, 8, 10), date(2026, 8, 10)))), [])


if __name__ == "__main__":
    unittest.main()
