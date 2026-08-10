"""Read-only Coupang purchase-order collector."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import hmac
from typing import Any
from urllib.parse import quote, urlencode

from hmr_order_collection.channels.base import ChannelAdapter, DateWindow
from hmr_order_collection.config import AppConfig
from hmr_order_collection.http import HttpClient, parse_json
from hmr_order_collection.masking import canonical_payload
from hmr_order_collection.models import ChannelRecord


BASE_URL = "https://api-gateway.coupang.com"
ORDER_STATUSES = (
    "ACCEPT",
    "INSTRUCT",
    "DEPARTURE",
    "DELIVERING",
    "FINAL_DELIVERY",
    "NONE_TRACKING",
)


def build_authorization(
    method: str,
    path: str,
    query: str,
    access_key: str,
    secret_key: str,
    signed_date: str,
) -> str:
    """Build Coupang's documented CEA HMAC-SHA256 Authorization header."""
    message = f"{signed_date}{method.upper()}{path}{query}".encode("ascii")
    signature = hmac.new(secret_key.encode("ascii"), message, hashlib.sha256).hexdigest()
    return (
        "CEA algorithm=HmacSHA256, "
        f"access-key={access_key}, signed-date={signed_date}, signature={signature}"
    )


class CoupangAdapter(ChannelAdapter):
    """Collect all six documented PO statuses using 31-day windows."""

    def __init__(
        self,
        config: AppConfig,
        *,
        http: HttpClient | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._vendor_id = config.require("COUPANG_VENDOR_ID")
        self._access_key = config.require("COUPANG_ACCESS_KEY")
        self._secret_key = config.require("COUPANG_SECRET_KEY")
        self._http = http or HttpClient()
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def fetch(self, window: DateWindow) -> Iterator[ChannelRecord]:
        inclusive_days = (window.end - window.start).days + 1
        if inclusive_days < 1 or inclusive_days > 31:
            raise ValueError("Coupang order windows must contain between 1 and 31 days")

        path = f"/v2/providers/openapi/apis/api/v5/vendors/{quote(self._vendor_id, safe='')}/ordersheets"
        for status in ORDER_STATUSES:
            params: dict[str, Any] = {
                "createdAtFrom": f"{window.start.isoformat()}+09:00",
                "createdAtTo": f"{window.end.isoformat()}+09:00",
                "maxPerPage": 50,
                "status": status,
            }
            seen_tokens: set[str] = set()
            while True:
                payload = self._get_page(path, params)
                if payload.get("code") != 200:
                    raise ValueError("Coupang order response reported a business failure")
                for shipment in payload.get("data") or []:
                    yield from _shipment_records(shipment)

                next_token = payload.get("nextToken")
                if next_token is None or next_token == "":
                    break
                token = str(next_token)
                if token in seen_tokens:
                    break
                seen_tokens.add(token)
                params["nextToken"] = token

    def _get_page(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        query = urlencode(params)
        now = self._clock()
        if now.tzinfo is None:
            raise ValueError("Coupang signing clock must return a timezone-aware datetime")
        signed_date = now.astimezone(timezone.utc).strftime("%y%m%dT%H%M%SZ")
        authorization = build_authorization(
            "GET", path, query, self._access_key, self._secret_key, signed_date
        )
        response = self._http.request(
            "GET",
            f"{BASE_URL}{path}",
            params=dict(params),
            headers={
                "Accept": "application/json",
                "Authorization": authorization,
                "Content-Type": "application/json;charset=UTF-8",
                "X-Requested-By": self._vendor_id,
            },
        )
        self._record_page()
        payload = parse_json(response)
        if not isinstance(payload, dict):
            raise ValueError("Coupang order response must be a JSON object")
        return payload


def _shipment_records(shipment: dict[str, Any]) -> Iterator[ChannelRecord]:
    shipment_box_id = str(shipment["shipmentBoxId"])
    order_status = shipment.get("status")
    for item in shipment.get("orderItems") or []:
        order_item_id = str(item["sequenceNo"])
        columns = {
            "ShipmentBoxId": shipment_box_id,
            "OrderId": _optional_str(shipment.get("orderId")),
            "OrderItemId": order_item_id,
            "VendorItemId": _optional_str(item.get("vendorItemId")),
            "SellerProductId": _optional_str(item.get("sellerProductId")),
            "SellerProductItemId": None,
            "ProductName": item.get("sellerProductName"),
            "OptionName": item.get("sellerProductItemName"),
            "Quantity": item.get("shippingCount"),
            "CanceledQuantity": item.get("cancelCount"),
            "SalesPrice": _money(item.get("salesPrice")),
            "OrderStatus": order_status,
            "DeliveryStatus": order_status,
            "OrderedAt": shipment.get("orderedAt"),
            "PaidAt": shipment.get("paidAt"),
            "EstimatedShippingAt": item.get("estimatedShippingDate"),
            "DispatchedAt": shipment.get("inTrasitDateTime"),
            "DeliveryCompletedAt": shipment.get("deliveredDate"),
            "DeliveryCompanyCode": shipment.get("deliveryCompanyName"),
            "TrackingNumber": shipment.get("invoiceNumber"),
            "RawOrderStatus": order_status,
            "RawDeliveryStatus": order_status,
        }
        raw_payload = {
            key: value
            for key, value in shipment.items()
            if key not in {"orderItems", "orderer", "receiver", "overseaShippingInfoDto"}
        }
        raw_payload.update(
            {
                "orderItem": item,
                "orderer": "***",
                "receiver": "***",
                "overseaShippingInfoDto": "***",
            }
        )
        raw_json, payload_hash = canonical_payload(raw_payload)
        yield ChannelRecord(
            (shipment_box_id, order_item_id), columns, raw_json, payload_hash
        )


def _money(value: Any) -> Decimal | None:
    if not isinstance(value, dict):
        return None
    units = Decimal(value.get("units", 0))
    nanos = Decimal(value.get("nanos", 0)) / Decimal(1_000_000_000)
    return units + nanos


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)
