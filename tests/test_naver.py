import json
from datetime import date
from pathlib import Path
from types import MappingProxyType
import unittest

import requests

from hmr_order_collection.channels.base import DateWindow
from hmr_order_collection.channels.naver import NaverAdapter, generate_client_secret_sign
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
                "NAVER_COMMERCE_CLIENT_ID": "aaaabbbbcccc",
                "NAVER_COMMERCE_CLIENT_SECRET": "$2b$04$abcdefghijklmnopqrstuu",
            }
        )
    )


class NaverAdapterTests(unittest.TestCase):
    def test_client_secret_signature_uses_the_documented_bcrypt_then_base64_algorithm(self):
        signature = generate_client_secret_sign(
            "aaaabbbbcccc", "$2b$04$abcdefghijklmnopqrstuu", 1643961623299
        )

        self.assertEqual(
            signature,
            "JDJiJDA0JGFiY2RlZmdoaWprbG1ub3BxcnN0dXV6NDlObEtMdDYyUWhPdnNjSTNNWnR4ZUlDQjNoYUpD",
        )

    def test_fetch_acquires_token_pages_changes_and_batches_details_at_300_ids(self):
        first_ids = [f"NAVER-PRODUCT-ORDER-{number:03d}" for number in range(1, 301)]
        final_id = "NAVER-PRODUCT-ORDER-301"

        def handler(method, url, kwargs):
            if url.endswith("/oauth2/token"):
                return {"access_token": "SYNTHETIC_ACCESS_TOKEN", "expires_in": 10800, "token_type": "Bearer"}
            if url.endswith("/last-changed-statuses"):
                if "moreSequence" not in kwargs["params"]:
                    return {
                        "data": {
                            "count": 300,
                            "lastChangeStatuses": [{"productOrderId": item_id} for item_id in first_ids],
                            "more": {
                                "moreFrom": "2026-08-10T12:00:00.000+09:00",
                                "moreSequence": final_id,
                            },
                        }
                    }
                return {"data": {"count": 1, "lastChangeStatuses": [{"productOrderId": final_id}]}}
            product_order_ids = kwargs["json"]["productOrderIds"]
            return {
                "data": [
                    {
                        "order": {"orderId": f"ORDER-{item_id}", "paymentDate": None},
                        "productOrder": {"productOrderId": item_id},
                        "delivery": {},
                    }
                    for item_id in product_order_ids
                ]
            }

        http = FakeHttpClient(handler)
        adapter = NaverAdapter(config(), http=http, clock_ms=lambda: 1643961623299)

        records = list(adapter.fetch(DateWindow(date(2026, 8, 10), date(2026, 8, 10))))

        self.assertEqual(len(records), 301)
        token_call = http.calls[0]
        self.assertEqual(token_call[0:2], ("POST", "https://api.commerce.naver.com/external/v1/oauth2/token"))
        self.assertEqual(
            token_call[2]["data"],
            {
                "client_id": "aaaabbbbcccc",
                "timestamp": 1643961623299,
                "grant_type": "client_credentials",
                "client_secret_sign": "JDJiJDA0JGFiY2RlZmdoaWprbG1ub3BxcnN0dXV6NDlObEtMdDYyUWhPdnNjSTNNWnR4ZUlDQjNoYUpD",
                "type": "SELF",
            },
        )
        changed_calls = [call for call in http.calls if call[1].endswith("/last-changed-statuses")]
        self.assertEqual(len(changed_calls), 2)
        self.assertEqual(changed_calls[1][2]["params"]["lastChangedFrom"], "2026-08-10T12:00:00.000+09:00")
        self.assertEqual(changed_calls[1][2]["params"]["moreSequence"], final_id)
        detail_calls = [call for call in http.calls if call[1].endswith("/product-orders/query")]
        self.assertEqual([len(call[2]["json"]["productOrderIds"]) for call in detail_calls], [300, 1])
        self.assertTrue(all(call[2]["json"]["quantityClaimCompatibility"] for call in detail_calls))

    def test_repeated_more_pair_stops_continuation_loop(self):
        page_count = 0

        def handler(method, url, kwargs):
            nonlocal page_count
            if url.endswith("/oauth2/token"):
                return {"access_token": "SYNTHETIC_ACCESS_TOKEN"}
            if url.endswith("/last-changed-statuses"):
                page_count += 1
                return {
                    "data": {
                        "lastChangeStatuses": [{"productOrderId": "NAVER-PRODUCT-ORDER-001"}],
                        "more": {"moreFrom": "2026-08-10T12:00:00.000+09:00", "moreSequence": "001"},
                    }
                }
            return {"data": []}

        adapter = NaverAdapter(config(), http=FakeHttpClient(handler), clock_ms=lambda: 1643961623299)

        list(adapter.fetch(DateWindow(date(2026, 8, 10), date(2026, 8, 10))))

        self.assertEqual(page_count, 2)

    def test_detail_maps_only_deployed_columns_and_masks_raw_payload(self):
        changed = fixture("naver_changed_page.json")
        detail = fixture("naver_product_order.json")

        def handler(method, url, kwargs):
            if url.endswith("/oauth2/token"):
                return {"access_token": "SYNTHETIC_ACCESS_TOKEN"}
            return changed if url.endswith("/last-changed-statuses") else detail

        record = next(
            NaverAdapter(config(), http=FakeHttpClient(handler), clock_ms=lambda: 1643961623299).fetch(
                DateWindow(date(2026, 8, 10), date(2026, 8, 10))
            )
        )

        self.assertEqual(record.identity, ("NAVER-PRODUCT-ORDER-001",))
        self.assertEqual(set(record.columns), set(TABLES["naver"].columns))
        self.assertEqual(
            dict(record.columns),
            {
                "ProductOrderId": "NAVER-PRODUCT-ORDER-001",
                "OrderId": "NAVER-ORDER-001",
                "ProductId": "NAVER-PRODUCT-001",
                "OptionId": "NAVER-ITEM-001",
                "ProductName": "Synthetic meal kit",
                "OptionName": "Two portions",
                "Quantity": 2,
                "UnitPrice": 12500,
                "TotalPaymentAmount": 24000,
                "ProductOrderStatus": "DELIVERED",
                "ClaimStatus": None,
                "DeliveryStatus": "DELIVERY_COMPLETION",
                "PaymentAt": "2026-08-09T10:01:00.000+09:00",
                "DispatchAt": "2026-08-09T18:00:00.000+09:00",
                "DeliveryCompletedAt": "2026-08-10T15:00:00.000+09:00",
                "DeliveryCompanyCode": "CJGLS",
                "TrackingNumber": "SYNTHETIC-TRACKING-001",
                "RawOrderStatus": "DELIVERED",
                "RawDeliveryStatus": "DELIVERY_COMPLETION",
            },
        )
        self.assertNotIn("SYNTHETIC_NAME_TO_MASK", record.raw_json)
        self.assertNotIn("SYNTHETIC_PHONE_TO_MASK", record.raw_json)
        self.assertIn('"ordererName":"***"', record.raw_json)

    def test_fetch_rejects_windows_longer_than_24_hours_before_http(self):
        http = FakeHttpClient(lambda *_: {})

        with self.assertRaisesRegex(ValueError, "24 hours"):
            list(
                NaverAdapter(config(), http=http, clock_ms=lambda: 1643961623299).fetch(
                    DateWindow(date(2026, 8, 9), date(2026, 8, 10))
                )
            )

        self.assertEqual(http.calls, [])


if __name__ == "__main__":
    unittest.main()
