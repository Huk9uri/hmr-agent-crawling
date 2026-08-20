import json
from datetime import date
from decimal import Decimal
from types import MappingProxyType
import unittest

import requests

from hmr_order_collection.channels.base import DateWindow
from hmr_order_collection.channels.cj_onstyle import CJ_ONSTYLE_DELIVERY_URL, CjOnstyleAdapter
from hmr_order_collection.config import AppConfig
from hmr_order_collection.database import TABLES


def config():
    return AppConfig(MappingProxyType({
        "CJ_ONSTYLE_VENDOR_CODE": "SYNTHETIC_VENDOR",
        "CJ_ONSTYLE_AUTHENTICATION_KEY": "SYNTHETIC_KEY",
    }))


def response(payload):
    result = requests.Response()
    result.status_code = 200
    result.url = CJ_ONSTYLE_DELIVERY_URL
    result._content = json.dumps(payload).encode("utf-8")
    return result


def row(**changes):
    value = {
        "orderNo": "CJ-ORDER-001", "orderItemSequence": 2,
        "orderDetailSequence": 3, "orderProcessingSequence": 4,
        "originalOrderNo": "CJ-ORIGINAL-001", "itemCode": "ITEM-1",
        "optionCode": "OPTION-1", "vendorItemCode": "VENDOR-1",
        "itemName": "Synthetic soup", "optionName": "Two packs",
        "webItemName": "Web soup", "packItemNm": "Cold pack",
        "packItemAvailability": "Y", "itemType": "1", "itemCategory": "FOOD",
        "count": "2", "supplyPrice": "10000", "salesPrice": "12000",
        "paymentPrice": "11500", "customerResponsibilityCost": "500",
        "deliveryStatus": "5", "deliveryInstructionCheck": "Y",
        "deliveryMethodName": "parcel", "deliveryType": "NORMAL",
        "orderType": "ORDER", "scheduledCancellation": "N",
        "deliveryInstructionDate": "2026-08-01 10:00:00",
        "expectedDeliveryDate": "2026-08-03", "deliveryDate": "2026-08-02 12:00:00",
        "deliveryCompletionDate": "2026-08-03 14:00:00",
        "deliveryCancelDate": None, "paymentDate": "2026-08-01 09:00:00",
        "courierCompany": "CJGLS", "waybillNo": "INVOICE-1",
        "waybillIdentifierNo": "WAYBILL-ID-1", "reasonForNonDelivery": None,
        "claimReason": None, "salesChannel": "WEB", "salesChannelName": "CJ온스타일",
        "earlyMorningDelivery": "N", "alreadyDeliveryStatus": "Y",
        "forcedDeliveryStatus": "N", "customerDesignationStatus": "N",
        "internationalShippingAvailability": "N", "affiliateItemName": "Affiliate soup",
        "affiliateItemCode": "AFF-1", "dpatBrandCd": "BR-1",
        "dpatBrandNm": "Hanchon", "dpatFlrhigtNm": "Fulfillment A",
        "recipient": "TO_MASK", "recipientName": "TO_MASK", "ordererName": "TO_MASK",
        "address": "TO_MASK", "postalCode": "TO_MASK",
        "ordererTelephoneNo": "TO_MASK", "recipientTelephoneNo": "TO_MASK",
        "recipientMobilePhoneNo": "TO_MASK", "deliveryLocation1": "TO_MASK",
        "deliveryLocation2": "TO_MASK", "deliveryNote": "TO_MASK",
        "sharedEntrancePassword": "TO_MASK", "personalClearanceCode": "TO_MASK",
        "giftDetails": "TO_MASK", "claimDetailedReason": "TO_MASK",
        "detailedReasonForNonDelivery": "TO_MASK",
    }
    value.update(changes)
    return value


class FakeHttp:
    def __init__(self, payloads):
        self.payloads = iter(payloads)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return response(next(self.payloads))


class CjOnstyleAdapterTests(unittest.TestCase):
    def test_fetch_calls_four_lifecycle_queries_deduplicates_and_masks_pii(self):
        http = FakeHttp([
            {"returnCode": "0000", "error": False, "data": [row(deliveryStatus="2")]},
            {"returnCode": "0000", "error": False, "data": [row(deliveryStatus="4")]},
            {"returnCode": "0000", "error": False, "data": [row()]},
            {"returnCode": "0000", "error": False, "data": []},
        ])
        adapter = CjOnstyleAdapter(config(), http=http)

        records = list(adapter.fetch(DateWindow(date(2026, 7, 11), date(2026, 8, 10))))

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.identity, ("CJ-ORDER-001", "2", "3", "4"))
        self.assertEqual(set(record.columns), set(TABLES["cj_onstyle"].columns))
        self.assertEqual(record.columns["Quantity"], 2)
        self.assertEqual(record.columns["PaymentPrice"], Decimal("11500"))
        self.assertEqual(record.columns["PackItemName"], "Cold pack")
        self.assertEqual(record.columns["DeliveryCompletedAt"], "2026-08-03 14:00:00")
        self.assertEqual(adapter.pages_fetched, 4)
        self.assertEqual(
            [(call[2]["json"]["dateType"], call[2]["json"]["deliveryStatus"]) for call in http.calls],
            [("2", "2"), ("3", "4"), ("4", "5"), ("6", "6")],
        )
        for method, url, kwargs in http.calls:
            self.assertEqual((method, url), ("POST", CJ_ONSTYLE_DELIVERY_URL))
            self.assertEqual(kwargs["headers"]["vendorCode"], "SYNTHETIC_VENDOR")
            self.assertEqual(kwargs["headers"]["authenticationKey"], "SYNTHETIC_KEY")
            self.assertEqual(kwargs["json"]["startDate"], "2026-07-11")
            self.assertEqual(kwargs["json"]["endDate"], "2026-08-10")
        masked = json.loads(record.raw_json)
        for key in ("recipient", "address", "deliveryNote", "giftDetails", "claimDetailedReason"):
            self.assertEqual(masked[key], "***")
        self.assertNotIn("TO_MASK", record.raw_json)

    def test_fetch_accepts_pack_item_name_live_variant(self):
        http = FakeHttp([
            {"returnCode": "0000", "error": False, "data": [row(packItemNm=None, packItemName="Live pack")]},
            *[{"returnCode": "0000", "error": False, "data": []}] * 3,
        ])
        record = next(CjOnstyleAdapter(config(), http=http).fetch(DateWindow(date(2026, 8, 10), date(2026, 8, 10))))
        self.assertEqual(record.columns["PackItemName"], "Live pack")

    def test_later_cancel_view_keeps_nonblank_dispatch_values(self):
        http = FakeHttp([
            {"returnCode": "0000", "error": False, "data": []},
            {"returnCode": "0000", "error": False, "data": [row(deliveryStatus="4")]},
            {"returnCode": "0000", "error": False, "data": []},
            {"returnCode": "0000", "error": False, "data": [row(deliveryStatus="6", deliveryDate=None, deliveryCancelDate="2026-08-04 10:00:00")]},
        ])
        record = next(CjOnstyleAdapter(config(), http=http).fetch(DateWindow(date(2026, 8, 1), date(2026, 8, 10))))
        self.assertEqual(record.columns["DispatchedAt"], "2026-08-02 12:00:00")
        self.assertEqual(record.columns["DeliveryCanceledAt"], "2026-08-04 10:00:00")
        self.assertEqual(record.columns["DeliveryStatus"], "6")

    def test_fetch_rejects_business_failure_and_malformed_data(self):
        for payload, message in (
            ({"returnCode": "9999", "error": True, "data": []}, "business failure"),
            ({"returnCode": "0000", "error": False, "data": {}}, "data list"),
        ):
            with self.subTest(payload=payload):
                with self.assertRaisesRegex(ValueError, message):
                    list(CjOnstyleAdapter(config(), http=FakeHttp([payload])).fetch(DateWindow(date(2026, 8, 10), date(2026, 8, 10))))

    def test_fetch_rejects_blank_identity(self):
        payload = {"returnCode": "0000", "error": False, "data": [row(orderNo="")]}
        with self.assertRaisesRegex(ValueError, "identity"):
            list(CjOnstyleAdapter(config(), http=FakeHttp([payload])).fetch(DateWindow(date(2026, 8, 10), date(2026, 8, 10))))

    def test_fetch_rejects_more_than_31_inclusive_days_before_http(self):
        http = FakeHttp([])
        with self.assertRaisesRegex(ValueError, "31 days"):
            list(CjOnstyleAdapter(config(), http=http).fetch(DateWindow(date(2026, 7, 10), date(2026, 8, 10))))
        self.assertEqual(http.calls, [])


if __name__ == "__main__":
    unittest.main()
