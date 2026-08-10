from datetime import date
from pathlib import Path
from types import MappingProxyType
import unittest

import requests

from hmr_order_collection.channels.base import DateWindow
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
    def test_fetch_follows_last_order_to_a_normal_final_page(self):
        http = FakeHttpClient(["godomall_orders_page.xml", "godomall_orders_last_page.xml"])

        records = list(GodomallAdapter(config(), http=http).fetch(DateWindow(date(2026, 8, 10), date(2026, 8, 10))))

        self.assertEqual(len(records), 3)
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
        self.assertNotIn("SYNTHETIC_NAME_TO_MASK", record.raw_json)
        self.assertNotIn("synthetic@example.invalid", record.raw_json)
        self.assertNotIn("SYNTHETIC_ADDRESS_TO_MASK", record.raw_json)
        self.assertNotIn("SYNTHETIC_SAFE_NUMBER_TO_MASK", record.raw_json)

    def test_successful_empty_response_returns_zero_records(self):
        http = FakeHttpClient(["godomall_empty_page.xml"])
        self.assertEqual(list(GodomallAdapter(config(), http=http).fetch(DateWindow(date(2026, 8, 10), date(2026, 8, 10)))), [])


if __name__ == "__main__":
    unittest.main()
