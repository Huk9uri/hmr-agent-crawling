import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
import unittest

import requests

from hmr_order_collection.channels.base import DateWindow
from hmr_order_collection.channels.ssg import (
    SSG_DELIVERY_END_URL,
    SSG_NON_DELIVERY_URL,
    SSG_ORDERS_URL,
    SsgAdapter,
)
from hmr_order_collection.config import AppConfig
from hmr_order_collection.database import TABLES


FIXTURES = Path(__file__).with_name("fixtures")


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def response(payload, url=SSG_ORDERS_URL):
    result = requests.Response()
    result.status_code = 200
    result.url = url
    result._content = json.dumps(payload).encode("utf-8")
    return result


class FakeHttpClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return response(self.payload, url)


class RoutingHttpClient:
    def __init__(self, payloads):
        self.payloads = payloads
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return response(self.payloads[url], url)


def config():
    return AppConfig(MappingProxyType({"SSG_API_KEY": "SYNTHETIC_SSG_API_KEY"}))


class SsgAdapterTests(unittest.TestCase):
    def test_fetch_enriches_official_fields_by_shipping_number(self):
        http = RoutingHttpClient({
            SSG_ORDERS_URL: fixture("ssg_shipping_directions.json"),
            SSG_NON_DELIVERY_URL: {
                "resultCode": "00",
                "resultMessage": "SUCCESS",
                "nonDeliverys": [{
                    "ordNo": "SSG-ORDER-001",
                    "ordItemSeq": 2,
                    "shppNo": "SSG-SHIPPING-001",
                    "shppSeq": 3,
                    "whoutDt": "2026-08-10 13:00:00",
                    "delicoVenId": "CJGLS",
                    "wblNo": "SSG-INVOICE-001",
                    "lastShppProgStatDtlCd": "43",
                }],
            },
            SSG_DELIVERY_END_URL: {
                "resultCode": "00",
                "resultMessage": "SUCCESS",
                "deliveryEnds": [{
                    "ordNo": "SSG-ORDER-001",
                    "ordItemSeq": 2,
                    "shppNo": "SSG-SHIPPING-001",
                    "shppSeq": 3,
                    "whoutDt": "2026-08-10 13:00:00",
                    "delicoVenId": "CJGLS",
                    "wblNo": "SSG-INVOICE-001",
                    "shppDt": "2026-08-11 09:00:00",
                    "lastShppProgStatDtlCd": "51",
                }],
            },
        })

        record = next(SsgAdapter(config(), http=http).fetch(DateWindow(date(2026, 8, 10), date(2026, 8, 10))))

        self.assertEqual(record.columns["WarehouseOutCompletedAt"], "2026-08-10 13:00:00")
        self.assertEqual(record.columns["DeliveryCompanyCode"], "CJGLS")
        self.assertEqual(record.columns["TrackingNumber"], "SSG-INVOICE-001")
        self.assertIsNone(record.columns["DeliveryTrackingStatusAt"])
        self.assertEqual(record.columns["DeliveryCompletedAt"], "2026-08-11 09:00:00")
        self.assertEqual(record.columns["ShippingProgressDetailCode"], "51")
        self.assertEqual(record.columns["RawDeliveryStatus"], "51")
        self.assertEqual(
            [call[1] for call in http.calls],
            [SSG_ORDERS_URL, SSG_NON_DELIVERY_URL, SSG_DELIVERY_END_URL],
        )
        for _, _, kwargs in http.calls[1:]:
            envelope = next(iter(kwargs["json"].values()))
            self.assertEqual(
                envelope,
                {"commType": "02", "commValue": "SSG-SHIPPING-001"},
            )

    def test_fetch_treats_blank_follow_up_stage_sentinel_as_empty(self):
        http = RoutingHttpClient({
            SSG_ORDERS_URL: fixture("ssg_shipping_directions.json"),
            SSG_NON_DELIVERY_URL: {
                "resultCode": "00",
                "resultMessage": "SUCCESS",
                "nonDeliverys": [""],
            },
            SSG_DELIVERY_END_URL: {
                "resultCode": "00",
                "resultMessage": "SUCCESS",
                "deliveryEnds": [""],
            },
        })

        records = list(
            SsgAdapter(config(), http=http).fetch(
                DateWindow(date(2026, 8, 10), date(2026, 8, 10))
            )
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].identity, ("SSG-ORDER-001", "2", "SSG-SHIPPING-001", "3"))

    def test_fetch_treats_blank_string_shipping_direction_sentinel_as_empty(self):
        payload = {
            "resultCode": "00",
            "resultMessage": "SUCCESS",
            "shppDirections": [""],
        }
        adapter = SsgAdapter(config(), http=FakeHttpClient(payload))

        try:
            records = list(
                adapter.fetch(DateWindow(date(2026, 8, 10), date(2026, 8, 10)))
            )
        except ValueError as error:
            self.fail(f"blank SSG shipping-direction sentinel was rejected: {error}")

        self.assertEqual(records, [])
        self.assertEqual(adapter.pages_fetched, 1)

    def test_fetch_rejects_nonblank_string_shipping_direction_sentinel(self):
        payload = {
            "resultCode": "00",
            "resultMessage": "SUCCESS",
            "shppDirections": ["synthetic malformed row"],
        }

        with self.assertRaisesRegex(ValueError, "list was malformed"):
            list(
                SsgAdapter(config(), http=FakeHttpClient(payload)).fetch(
                    DateWindow(date(2026, 8, 10), date(2026, 8, 10))
                )
            )

    def test_fetch_posts_order_completion_window_and_maps_only_deployed_columns(self):
        http = FakeHttpClient(fixture("ssg_shipping_directions.json"))
        adapter = SsgAdapter(config(), http=http)

        record = next(
            adapter.fetch(
                DateWindow(date(2026, 2, 12), date(2026, 8, 10))
            )
        )
        self.assertEqual(adapter.pages_fetched, 3)

        self.assertEqual(len(http.calls), 3)
        self.assertEqual(
            http.calls[0],
                (
                    "POST",
                    SSG_ORDERS_URL,
                    {
                        "headers": {
                            "Accept": "application/json",
                            "Authorization": "SYNTHETIC_SSG_API_KEY",
                            "Content-Type": "application/json",
                        },
                        "json": {
                            "requestShppDirection": {
                                "perdType": "02",
                                "perdStrDts": "2026-02-12",
                                "perdEndDts": "2026-08-10",
                            }
                        },
                    },
                ),
        )
        self.assertEqual(record.identity, ("SSG-ORDER-001", "2", "SSG-SHIPPING-001", "3"))
        self.assertEqual(set(record.columns), set(TABLES["ssg"].columns))
        self.assertEqual(
            dict(record.columns),
            {
                "OrdNo": "SSG-ORDER-001",
                "OrdItemSeq": "2",
                "ShppNo": "SSG-SHIPPING-001",
                "ShppSeq": "3",
                "SiteNo": "6005",
                "ItemId": "SSG-ITEM-001",
                "UitemId": "SSG-UNIT-001",
                "SplVenItemId": "SSG-VENDOR-ITEM-001",
                "USplVenItemId": "SSG-VENDOR-UNIT-001",
                "ItemName": "Synthetic meal kit",
                "UnitItemName": "Two portions",
                "OrderQuantity": 4,
                "DirectedQuantity": 3,
                "CanceledQuantity": 1,
                "SupplyPrice": Decimal("10000"),
                "SalesPrice": Decimal("12500"),
                "RealOrderAmount": Decimal("11800"),
                "DiscountAmount": Decimal("700"),
                "OrderStatusCode": "120",
                "ShippingStatusCode": "10",
                "ShippingProgressDetailCode": "11",
                "OrderReceivedAt": "2026-08-09 10:00:00",
                "OrderCompletedAt": "2026-08-09 10:01:00",
                "ScheduledShippingDate": "2026-08-10",
                "WarehouseOutCompletedAt": None,
                "DeliveryCompanyCode": None,
                "TrackingNumber": None,
                "DeliveryTrackingStatusAt": None,
                "DeliveryCompletedAt": None,
                "RawOrderStatus": "120",
                "RawDeliveryStatus": "11",
            },
        )
        raw = json.loads(record.raw_json)
        private_keys = (
            "ordShpplocId",
            "ordpeNm",
            "ordpeHpno",
            "rcptpeNm",
            "rcptpeHpno",
            "rcptpeTelno",
            "shpplocAddr",
            "shpplocZipcd",
            "shpplocOldZipcd",
            "ordpeRoadAddr",
            "shpplocBascAddr",
            "shpplocDtlAddr",
            "pCus",
            "mbrLoginId",
            "ordMemoCntt",
        )
        self.assertTrue(all(raw[key] == "***" for key in private_keys))
        self.assertNotIn("TO_MASK", record.raw_json)

    def test_fetch_rejects_non_success_result_code_even_on_http_200(self):
        http = FakeHttpClient(
            {"resultCode": "99", "resultMessage": "FAIL", "resultDesc": "synthetic failure"}
        )

        with self.assertRaisesRegex(ValueError, "business failure"):
            list(
                SsgAdapter(config(), http=http).fetch(
                    DateWindow(date(2026, 8, 10), date(2026, 8, 10))
                )
            )

    def test_fetch_rejects_null_or_empty_identity_components(self):
        cases = fixture("ssg_invalid_identities.json")["invalidRows"]

        for case in cases:
            with self.subTest(component=case["component"]):
                payload = {
                    "resultCode": "00",
                    "resultMessage": "SUCCESS",
                    "resultDesc": "synthetic success",
                    "shppDirections": [{"shppDirection": case["row"]}],
                }
                with self.assertRaisesRegex(ValueError, "identity"):
                    list(
                        SsgAdapter(config(), http=FakeHttpClient(payload)).fetch(
                            DateWindow(date(2026, 8, 10), date(2026, 8, 10))
                        )
                    )

    def test_fetch_rejects_windows_longer_than_180_inclusive_days_before_http(self):
        http = FakeHttpClient({})

        with self.assertRaisesRegex(ValueError, "180 days"):
            list(
                SsgAdapter(config(), http=http).fetch(
                    DateWindow(date(2026, 2, 11), date(2026, 8, 10))
                )
            )

        self.assertEqual(http.calls, [])


if __name__ == "__main__":
    unittest.main()
