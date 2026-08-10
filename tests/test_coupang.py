import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
import unittest

import requests

from hmr_order_collection.channels.base import DateWindow
from hmr_order_collection.channels.coupang import CoupangAdapter, ORDER_STATUSES, build_authorization
from hmr_order_collection.config import AppConfig
from hmr_order_collection.database import TABLES


FIXTURES = Path(__file__).with_name("fixtures")


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def response(payload, url="https://synthetic.invalid"):
    result = requests.Response()
    result.status_code = 200
    result.url = url
    result._content = json.dumps(payload).encode("utf-8")
    return result


class FakeHttpClient:
    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return response(self.handler(method, url, kwargs), url)


def config():
    return AppConfig(
        MappingProxyType(
            {
                "COUPANG_VENDOR_ID": "SYNTHETIC_VENDOR",
                "COUPANG_ACCESS_KEY": "SYNTHETIC_ACCESS_KEY",
                "COUPANG_SECRET_KEY": "SYNTHETIC_SECRET_KEY",
            }
        )
    )


NOW = datetime(2026, 8, 10, 3, 4, 5, tzinfo=timezone.utc)


class CoupangAdapterTests(unittest.TestCase):
    def test_authorization_matches_literal_hmac_sha256_vector(self):
        authorization = build_authorization(
            "GET",
            "/v2/providers/openapi/apis/api/v5/vendors/SYNTHETIC_VENDOR/ordersheets",
            "createdAtFrom=2026-08-01%2B09%3A00&createdAtTo=2026-08-10%2B09%3A00&maxPerPage=50&status=ACCEPT",
            "SYNTHETIC_ACCESS_KEY",
            "SYNTHETIC_SECRET_KEY",
            "260810T030405Z",
        )

        self.assertEqual(
            authorization,
            "CEA algorithm=HmacSHA256, access-key=SYNTHETIC_ACCESS_KEY, signed-date=260810T030405Z, "
            "signature=0416af616b4141adc4f85ccb20874c3d3d29391f146715fed2c15d294cb81647",
        )

    def test_fetch_queries_all_statuses_and_stops_a_repeated_next_token(self):
        pages_by_status = {status: 0 for status in ORDER_STATUSES}

        def handler(method, url, kwargs):
            status = kwargs["params"]["status"]
            pages_by_status[status] += 1
            if status == "ACCEPT":
                return {"code": 200, "message": "OK", "data": [], "nextToken": "SAME-TOKEN"}
            return fixture("coupang_empty_page.json")

        http = FakeHttpClient(handler)
        adapter = CoupangAdapter(config(), http=http, clock=lambda: NOW)

        records = list(adapter.fetch(DateWindow(date(2026, 8, 1), date(2026, 8, 10))))

        self.assertEqual(records, [])
        self.assertEqual(pages_by_status, {"ACCEPT": 2, "INSTRUCT": 1, "DEPARTURE": 1, "DELIVERING": 1, "FINAL_DELIVERY": 1, "NONE_TRACKING": 1})
        self.assertEqual(http.calls[0][2]["params"], {"createdAtFrom": "2026-08-01+09:00", "createdAtTo": "2026-08-10+09:00", "maxPerPage": 50, "status": "ACCEPT"})
        self.assertEqual(http.calls[1][2]["params"]["nextToken"], "SAME-TOKEN")
        self.assertTrue(all(call[0] == "GET" for call in http.calls))
        self.assertTrue(all(call[2]["headers"]["X-Requested-By"] == "SYNTHETIC_VENDOR" for call in http.calls))

    def test_order_item_maps_only_deployed_columns_and_masks_raw_payload(self):
        order_page = fixture("coupang_orders_page.json")

        def handler(method, url, kwargs):
            return order_page if kwargs["params"]["status"] == "ACCEPT" else fixture("coupang_empty_page.json")

        record = next(
            CoupangAdapter(config(), http=FakeHttpClient(handler), clock=lambda: NOW).fetch(
                DateWindow(date(2026, 8, 1), date(2026, 8, 10))
            )
        )

        self.assertEqual(record.identity, ("COUPANG-SHIPMENT-001", "001"))
        self.assertEqual(set(record.columns), set(TABLES["coupang"].columns))
        self.assertEqual(
            dict(record.columns),
            {
                "ShipmentBoxId": "COUPANG-SHIPMENT-001",
                "OrderId": "COUPANG-ORDER-001",
                "OrderItemId": "001",
                "VendorItemId": "COUPANG-VENDOR-ITEM-001",
                "SellerProductId": "COUPANG-SELLER-PRODUCT-001",
                "SellerProductItemId": None,
                "ProductName": "Synthetic meal kit",
                "OptionName": "Two portions",
                "Quantity": 2,
                "CanceledQuantity": 1,
                "SalesPrice": Decimal("12900.25"),
                "OrderStatus": "FINAL_DELIVERY",
                "DeliveryStatus": "FINAL_DELIVERY",
                "OrderedAt": "2026-08-09T10:00:00.000000+09:00",
                "PaidAt": "2026-08-09T10:01:00.000000+09:00",
                "EstimatedShippingAt": "2026-08-10",
                "DispatchedAt": "2026-08-09T18:00:00.000000+09:00",
                "DeliveryCompletedAt": "2026-08-10T15:00:00.000000+09:00",
                "DeliveryCompanyCode": "CJ Logistics",
                "TrackingNumber": "SYNTHETIC-INVOICE-001",
                "RawOrderStatus": "FINAL_DELIVERY",
                "RawDeliveryStatus": "FINAL_DELIVERY",
            },
        )
        for private_value in (
            "SYNTHETIC_NAME_TO_MASK",
            "SYNTHETIC_EMAIL_TO_MASK",
            "SYNTHETIC_PHONE_TO_MASK",
            "SYNTHETIC_ADDRESS_TO_MASK",
            "SYNTHETIC_CUSTOMS_TO_MASK",
        ):
            self.assertNotIn(private_value, record.raw_json)
        self.assertIn('"receiver":"***"', record.raw_json)

    def test_fetch_rejects_windows_longer_than_31_days_before_http(self):
        http = FakeHttpClient(lambda *_: {})

        with self.assertRaisesRegex(ValueError, "31 days"):
            list(
                CoupangAdapter(config(), http=http, clock=lambda: NOW).fetch(
                    DateWindow(date(2026, 7, 10), date(2026, 8, 10))
                )
            )

        self.assertEqual(http.calls, [])


if __name__ == "__main__":
    unittest.main()
