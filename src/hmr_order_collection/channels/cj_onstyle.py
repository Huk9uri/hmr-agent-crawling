"""Read-only CJ OnStyle delivery lifecycle collector."""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal, InvalidOperation
from typing import Any

from hmr_order_collection.channels.base import ChannelAdapter, DateWindow
from hmr_order_collection.config import AppConfig
from hmr_order_collection.http import HttpClient, parse_json
from hmr_order_collection.masking import canonical_payload
from hmr_order_collection.models import ChannelRecord


CJ_ONSTYLE_DELIVERY_URL = "https://ingress-api.cjoshopping.com/delivery/getDeliveryList"
_LIFECYCLE_QUERIES = (("2", "2"), ("3", "4"), ("4", "5"), ("6", "6"))
_PRIVATE_FIELDS = frozenset({
    "recipient", "recipientName", "ordererName", "address", "postalCode",
    "ordererTelephoneNo", "recipientTelephoneNo", "recipientMobilePhoneNo",
    "deliveryLocation1", "deliveryLocation2", "deliveryNote",
    "sharedEntrancePassword", "personalClearanceCode", "giftDetails",
    "claimDetailedReason", "detailedReasonForNonDelivery",
})


class CjOnstyleAdapter(ChannelAdapter):
    """Collect four documented delivery lifecycle views and merge by item identity."""

    def __init__(self, config: AppConfig, *, http: HttpClient | None = None) -> None:
        self._vendor_code = config.require("CJ_ONSTYLE_VENDOR_CODE")
        self._authentication_key = config.require("CJ_ONSTYLE_AUTHENTICATION_KEY")
        self._http = http or HttpClient()

    def fetch(self, window: DateWindow) -> Iterator[ChannelRecord]:
        inclusive_days = (window.end - window.start).days + 1
        if inclusive_days < 1 or inclusive_days > 31:
            raise ValueError("CJ OnStyle order windows must contain between 1 and 31 days")
        headers = {
            "Accept": "application/json", "Content-Type": "application/json",
            "vendorCode": self._vendor_code,
            "authenticationKey": self._authentication_key,
        }
        merged: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        for date_type, delivery_status in _LIFECYCLE_QUERIES:
            response = self._http.request(
                "POST", CJ_ONSTYLE_DELIVERY_URL, headers=dict(headers),
                json={
                    "dateType": date_type, "startDate": window.start.isoformat(),
                    "endDate": window.end.isoformat(), "deliveryStatus": delivery_status,
                },
            )
            for row in _rows(self, response):
                identity = _identity(row)
                if identity in merged:
                    merged[identity].update(
                        {key: value for key, value in row.items() if value is not None and value != ""}
                    )
                else:
                    merged[identity] = dict(row)
        for row in merged.values():
            yield _map_record(row)


def _rows(adapter: CjOnstyleAdapter, response: Any) -> list[dict[str, Any]]:
    adapter._record_page()
    payload = parse_json(response)
    if not isinstance(payload, dict):
        raise ValueError("CJ OnStyle response must be a JSON object")
    if payload.get("returnCode") not in ("0000", "OK") or payload.get("error") is True:
        raise ValueError("CJ OnStyle response reported a business failure")
    data = payload.get("data")
    if data is None:
        return []
    if not isinstance(data, list) or any(not isinstance(row, dict) for row in data):
        raise ValueError("CJ OnStyle response data list was malformed")
    return data


def _identity(row: dict[str, Any]) -> tuple[str, str, str, str]:
    keys = ("orderNo", "orderItemSequence", "orderDetailSequence", "orderProcessingSequence")
    values = tuple(row.get(key) for key in keys)
    if any(value is None or str(value).strip() == "" for value in values):
        raise ValueError("CJ OnStyle row lacked order item identity")
    return tuple(str(value) for value in values)


def _map_record(row: dict[str, Any]) -> ChannelRecord:
    identity = _identity(row)
    delivery_status = _optional_str(row.get("deliveryStatus"))
    order_type = _optional_str(row.get("orderType"))
    columns = {
        "OrderNo": identity[0], "OrderItemSequence": identity[1],
        "OrderDetailSequence": identity[2], "OrderProcessingSequence": identity[3],
        "OriginalOrderNo": _optional_str(row.get("originalOrderNo")),
        "ItemCode": _optional_str(row.get("itemCode")), "OptionCode": _optional_str(row.get("optionCode")),
        "VendorItemCode": _optional_str(row.get("vendorItemCode")), "ItemName": row.get("itemName"),
        "OptionName": row.get("optionName"), "WebItemName": row.get("webItemName"),
        "PackItemName": row.get("packItemName") or row.get("packItemNm"),
        "PackItemAvailability": _optional_str(row.get("packItemAvailability")),
        "ItemType": _optional_str(row.get("itemType")), "ItemCategory": _optional_str(row.get("itemCategory")),
        "Quantity": _integer(row.get("count")), "SupplyPrice": _decimal(row.get("supplyPrice")),
        "SalesPrice": _decimal(row.get("salesPrice")), "PaymentPrice": _decimal(row.get("paymentPrice")),
        "CustomerResponsibilityCost": _decimal(row.get("customerResponsibilityCost")),
        "DeliveryStatus": delivery_status, "DeliveryInstructionCheck": _optional_str(row.get("deliveryInstructionCheck")),
        "DeliveryMethodName": row.get("deliveryMethodName"), "DeliveryType": _optional_str(row.get("deliveryType")),
        "OrderType": order_type, "ScheduledCancellation": _optional_str(row.get("scheduledCancellation")),
        "DeliveryInstructionAt": row.get("deliveryInstructionDate"), "ExpectedDeliveryDate": row.get("expectedDeliveryDate"),
        "DispatchedAt": row.get("deliveryDate"), "DeliveryCompletedAt": row.get("deliveryCompletionDate"),
        "DeliveryCanceledAt": row.get("deliveryCancelDate"), "PaidAt": row.get("paymentDate"),
        "DeliveryCompanyCode": _optional_str(row.get("courierCompany")), "TrackingNumber": _optional_str(row.get("waybillNo")),
        "WaybillIdentifierNo": _optional_str(row.get("waybillIdentifierNo")),
        "ReasonForNonDelivery": row.get("reasonForNonDelivery"), "ClaimReason": row.get("claimReason"),
        "SalesChannel": _optional_str(row.get("salesChannel")), "SalesChannelName": row.get("salesChannelName"),
        "EarlyMorningDelivery": _optional_str(row.get("earlyMorningDelivery")),
        "AlreadyDeliveryStatus": _optional_str(row.get("alreadyDeliveryStatus")),
        "ForcedDeliveryStatus": _optional_str(row.get("forcedDeliveryStatus")),
        "CustomerDesignationStatus": _optional_str(row.get("customerDesignationStatus")),
        "InternationalShippingAvailability": _optional_str(row.get("internationalShippingAvailability")),
        "AffiliateItemName": row.get("affiliateItemName"), "AffiliateItemCode": _optional_str(row.get("affiliateItemCode")),
        "BrandCode": _optional_str(row.get("dpatBrandCd")), "BrandName": row.get("dpatBrandNm"),
        "FulfillmentName": row.get("dpatFlrhigtNm"), "RawOrderStatus": order_type,
        "RawDeliveryStatus": delivery_status,
    }
    raw_json, payload_hash = canonical_payload(_mask_private_fields(row))
    return ChannelRecord(identity, columns, raw_json, payload_hash)


def _mask_private_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: "***" if key in _PRIVATE_FIELDS else _mask_private_fields(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_mask_private_fields(item) for item in value]
    return value


def _optional_str(value: Any) -> str | None:
    return None if value is None or value == "" else str(value)


def _integer(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(Decimal(str(value)))
    except (InvalidOperation, ValueError) as error:
        raise ValueError("CJ OnStyle numeric field was invalid") from error


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError("CJ OnStyle numeric field was invalid") from error
