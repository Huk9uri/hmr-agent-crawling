from datetime import date
from pathlib import Path
from types import MappingProxyType
import unittest

import requests

from hmr_order_collection.channels.base import DateWindow
from hmr_order_collection.channels.elevenst import ORDER_ENDPOINTS, ElevenstAdapter
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
    def __init__(self, first_fixture="elevenst_empty.xml"):
        self.first_fixture = first_fixture
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        fixture = self.first_fixture if len(self.calls) == 1 else "elevenst_empty.xml"
        return response(fixture, url)


def config():
    return AppConfig(MappingProxyType({"ELEVENST_API_KEY": "SYNTHETIC_ELEVENST_KEY"}))


class ElevenstAdapterTests(unittest.TestCase):
    def test_namespaced_xml_emits_one_record_per_order_product_and_masks_raw_payload(self):
        http = FakeHttpClient("elevenst_namespaced_orders.xml")

        records = list(ElevenstAdapter(config(), http=http).fetch(DateWindow(date(2026, 8, 10), date(2026, 8, 10))))

        self.assertEqual([record.identity for record in records], [("ELEVENST-ORDER-001", "ELEVENST-ITEM-001"), ("ELEVENST-ORDER-001", "ELEVENST-ITEM-002")])
        self.assertTrue(all(set(record.columns) == set(TABLES["elevenst"].columns) for record in records))
        self.assertEqual(records[0].columns["ProductId"], "ELEVENST-PRODUCT-001")
        self.assertEqual(records[0].columns["Quantity"], 2)
        self.assertNotIn("SYNTHETIC_NAME_TO_MASK", records[0].raw_json)
        self.assertNotIn("SYNTHETIC_ABBREVIATED_NAME_TO_MASK", records[0].raw_json)
        self.assertNotIn("010-0000-0000", records[0].raw_json)

    def test_fetch_uses_only_read_only_order_endpoints_and_openapikey_header(self):
        http = FakeHttpClient()

        self.assertEqual(list(ElevenstAdapter(config(), http=http).fetch(DateWindow(date(2026, 8, 10), date(2026, 8, 10)))), [])

        self.assertEqual(len(http.calls), len(ORDER_ENDPOINTS))
        self.assertTrue(all(call[0] == "GET" for call in http.calls))
        self.assertTrue(all(call[2]["headers"] == {"Accept": "application/xml", "openapikey": "SYNTHETIC_ELEVENST_KEY"} for call in http.calls))
        self.assertEqual(
            [call[1] for call in http.calls],
            [f"{endpoint}/20260810/20260810" for endpoint in ORDER_ENDPOINTS],
        )

    def test_successful_empty_namespaced_responses_return_zero_records(self):
        self.assertEqual(list(ElevenstAdapter(config(), http=FakeHttpClient()).fetch(DateWindow(date(2026, 8, 10), date(2026, 8, 10)))), [])


if __name__ == "__main__":
    unittest.main()
