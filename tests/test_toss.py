import json
from datetime import date
from pathlib import Path
from types import MappingProxyType
import unittest

import requests

from hmr_order_collection.channels.base import DateWindow
from hmr_order_collection.channels.toss import ORDERS_URL, TOKEN_URL, TossShoppingAdapter
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
                "TOSS_SHOPPING_ACCESS_KEY": "SYNTHETIC_TOSS_ACCESS_KEY",
                "TOSS_SHOPPING_SECRET_KEY": "SYNTHETIC_TOSS_SECRET_KEY",
            }
        )
    )


class TossShoppingAdapterTests(unittest.TestCase):
    def test_fetch_uses_client_credentials_pages_to_null_and_refreshes_only_near_expiry(self):
        now = [1000.0]
        issued_tokens = []

        def handler(method, url, kwargs):
            if url == TOKEN_URL:
                token = f"SYNTHETIC_TOKEN_{len(issued_tokens) + 1}"
                issued_tokens.append(token)
                return {
                    "access_token": token,
                    "scope": "toss-shopping-fep:write",
                    "token_type": "Bearer",
                    "expires_in": 60,
                }
            if "nextCursor" not in kwargs["params"]:
                return {"resultType": "SUCCESS", "success": {"results": [], "nextCursor": "CURSOR-1"}}
            return {"resultType": "SUCCESS", "success": {"results": [], "nextCursor": None}}

        http = FakeHttpClient(handler)
        adapter = TossShoppingAdapter(config(), http=http, clock=lambda: now[0])
        window = DateWindow(date(2026, 7, 11), date(2026, 8, 10))

        list(adapter.fetch(window))
        now[0] = 1029.0
        list(adapter.fetch(window))
        now[0] = 1030.0
        list(adapter.fetch(window))

        token_calls = [call for call in http.calls if call[1] == TOKEN_URL]
        self.assertEqual(len(token_calls), 2)
        self.assertEqual(
            token_calls[0],
            (
                "POST",
                TOKEN_URL,
                {
                    "headers": {
                        "Accept": "application/json",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    "data": {
                        "grant_type": "client_credentials",
                        "client_id": "SYNTHETIC_TOSS_ACCESS_KEY",
                        "client_secret": "SYNTHETIC_TOSS_SECRET_KEY",
                        "scope": "toss-shopping-fep:write",
                    },
                },
            ),
        )
        order_calls = [call for call in http.calls if call[1] == ORDERS_URL]
        self.assertEqual(len(order_calls), 6)
        self.assertEqual(
            order_calls[0][2]["params"],
            {"startDate": "2026-07-11", "endDate": "2026-08-10", "limit": 50},
        )
        self.assertEqual(order_calls[1][2]["params"]["nextCursor"], "CURSOR-1")
        self.assertEqual(order_calls[0][2]["headers"]["Authorization"], "Bearer SYNTHETIC_TOKEN_1")
        self.assertEqual(order_calls[-1][2]["headers"]["Authorization"], "Bearer SYNTHETIC_TOKEN_2")
        self.assertTrue(all(call[0] == "GET" for call in order_calls))

    def test_order_maps_only_deployed_columns_and_masks_documented_private_fields(self):
        page = fixture("toss_orders_page.json")

        def handler(method, url, kwargs):
            if url == TOKEN_URL:
                return {"access_token": "SYNTHETIC_TOKEN", "expires_in": 3600}
            if "nextCursor" in kwargs["params"]:
                return {"resultType": "SUCCESS", "success": {"results": [], "nextCursor": None}}
            return page

        record = next(
            TossShoppingAdapter(config(), http=FakeHttpClient(handler), clock=lambda: 1000.0).fetch(
                DateWindow(date(2026, 8, 1), date(2026, 8, 10))
            )
        )

        self.assertEqual(record.identity, (20001,))
        self.assertEqual(set(record.columns), set(TABLES["toss"].columns))
        self.assertEqual(
            dict(record.columns),
            {
                "OrderId": 10001,
                "OrderProductId": 20001,
                "ProductId": 30001,
                "StockId": 40001,
                "ProductName": "Synthetic meal kit",
                "OptionName": "Two portions",
                "Quantity": 2,
                "Price": 12000,
                "OriginPrice": 15000,
                "TotalDiscountPrice": 3000,
                "TossShoppingDiscount": 1500,
                "TossPayDiscount": 1000,
                "TossPayPoint": 500,
                "OrderProductStatus": "DELIVERED",
                "OrderedAt": "2026-08-09T10:00:00.000Z",
                "CanceledAt": None,
                "ConfirmedAt": "2026-08-10T03:00:00.000Z",
                "ShippingDeadlineAt": "2026-08-11T00:00:00.000Z",
                "DeliveryCompanyCode": "CJGLS",
                "ShippingTrackingNumber": "SYNTHETIC-TOSS-TRACKING-001",
                "DeliveryFeeGroupId": 50001,
                "DeliveryFee": 3000,
                "DeliveryLocationType": "NORMAL",
                "NormalDeliveryFee": 3000,
                "JejuDeliveryFee": 5000,
                "MountainDeliveryFee": 5000,
                "ProductManagementCode": "TOSS-PRODUCT-001",
                "ProductItemManagementCode": "TOSS-OPTION-001",
                "RawOrderStatus": "DELIVERED",
                "RawDeliveryStatus": "DELIVERED",
            },
        )
        raw = json.loads(record.raw_json)
        private_keys = (
            "ordererName",
            "ordererPhone",
            "ordererRealPhone",
            "receiverName",
            "receiverPhone",
            "receiverRealPhone",
            "address",
            "detailAddress",
            "zipCode",
            "shippingNote",
        )
        self.assertTrue(all(raw[key] == "***" for key in private_keys))
        self.assertNotIn("TO_MASK", record.raw_json)

    def test_short_lived_valid_token_refreshes_halfway_through_its_lifetime(self):
        now = [1000.0]
        token_count = 0

        def handler(method, url, kwargs):
            nonlocal token_count
            if url == TOKEN_URL:
                token_count += 1
                return {"access_token": f"SHORT_TOKEN_{token_count}", "expires_in": 20}
            return {"resultType": "SUCCESS", "success": {"results": [], "nextCursor": None}}

        adapter = TossShoppingAdapter(
            config(), http=FakeHttpClient(handler), clock=lambda: now[0]
        )
        window = DateWindow(date(2026, 8, 10), date(2026, 8, 10))

        list(adapter.fetch(window))
        now[0] = 1009.0
        list(adapter.fetch(window))
        now[0] = 1010.0
        list(adapter.fetch(window))

        self.assertEqual(token_count, 2)

    def test_fetch_rejects_fail_result_type_even_on_http_200(self):
        def handler(method, url, kwargs):
            if url == TOKEN_URL:
                return {"access_token": "SYNTHETIC_TOKEN", "expires_in": 3600}
            return {
                "resultType": "FAIL",
                "error": {"errorCode": "INVALID_REQUEST", "reason": "synthetic failure"},
            }

        with self.assertRaisesRegex(ValueError, "business failure"):
            list(
                TossShoppingAdapter(config(), http=FakeHttpClient(handler), clock=lambda: 1000.0).fetch(
                    DateWindow(date(2026, 8, 1), date(2026, 8, 10))
                )
            )

    def test_fetch_raises_on_repeated_next_cursor_instead_of_returning_partial_success(self):
        def handler(method, url, kwargs):
            if url == TOKEN_URL:
                return {"access_token": "SYNTHETIC_TOKEN", "expires_in": 3600}
            return {
                "resultType": "SUCCESS",
                "success": {"results": [], "nextCursor": "REPEATED-CURSOR"},
            }

        http = FakeHttpClient(handler)

        with self.assertRaisesRegex(ValueError, "repeated nextCursor"):
            list(
                TossShoppingAdapter(config(), http=http, clock=lambda: 1000.0).fetch(
                    DateWindow(date(2026, 8, 1), date(2026, 8, 10))
                )
            )

        self.assertEqual(len([call for call in http.calls if call[1] == ORDERS_URL]), 2)

    def test_fetch_rejects_windows_longer_than_31_inclusive_days_before_http(self):
        http = FakeHttpClient(lambda *_: {})

        with self.assertRaisesRegex(ValueError, "31 days"):
            list(
                TossShoppingAdapter(config(), http=http, clock=lambda: 1000.0).fetch(
                    DateWindow(date(2026, 7, 10), date(2026, 8, 10))
                )
            )

        self.assertEqual(http.calls, [])


if __name__ == "__main__":
    unittest.main()
