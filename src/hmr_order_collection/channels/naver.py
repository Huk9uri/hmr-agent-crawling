"""Read-only Naver Commerce changed-order collector."""

from __future__ import annotations

import base64
from collections.abc import Callable, Iterator
from datetime import date
import time
from typing import Any

import bcrypt

from hmr_order_collection.channels.base import ChannelAdapter, DateWindow
from hmr_order_collection.config import AppConfig
from hmr_order_collection.http import HttpClient, parse_json
from hmr_order_collection.masking import canonical_payload
from hmr_order_collection.models import ChannelRecord


BASE_URL = "https://api.commerce.naver.com/external"
TOKEN_URL = f"{BASE_URL}/v1/oauth2/token"
CHANGED_ORDERS_URL = f"{BASE_URL}/v1/pay-order/seller/product-orders/last-changed-statuses"
DETAILS_URL = f"{BASE_URL}/v1/pay-order/seller/product-orders/query"
MAX_DETAIL_IDS = 300


def generate_client_secret_sign(client_id: str, client_secret: str, timestamp_ms: int) -> str:
    """Create Naver's documented bcrypt signature and standard Base64 encoding."""
    password = f"{client_id}_{timestamp_ms}".encode("utf-8")
    hashed = bcrypt.hashpw(password, client_secret.encode("utf-8"))
    return base64.b64encode(hashed).decode("ascii")


def _day_start(value: date) -> str:
    return f"{value.isoformat()}T00:00:00.000+09:00"


def _day_end(value: date) -> str:
    return f"{value.isoformat()}T23:59:59.999+09:00"


class NaverAdapter(ChannelAdapter):
    """Collect one 24-hour slice of changed SmartStore product orders."""

    def __init__(
        self,
        config: AppConfig,
        *,
        http: HttpClient | None = None,
        clock_ms: Callable[[], int] | None = None,
    ) -> None:
        self._client_id = config.require("NAVER_COMMERCE_CLIENT_ID")
        self._client_secret = config.require("NAVER_COMMERCE_CLIENT_SECRET")
        self._http = http or HttpClient()
        self._clock_ms = clock_ms or (lambda: time.time_ns() // 1_000_000)

    def fetch(self, window: DateWindow) -> Iterator[ChannelRecord]:
        if window.start != window.end:
            raise ValueError("Naver changed-order windows must be at most 24 hours")

        token = self._access_token()
        headers = {"Accept": "application/json", "Authorization": f"Bearer {token}"}
        product_order_ids = self._changed_product_order_ids(window, headers)
        for offset in range(0, len(product_order_ids), MAX_DETAIL_IDS):
            batch = product_order_ids[offset : offset + MAX_DETAIL_IDS]
            response = self._http.request(
                "POST",
                DETAILS_URL,
                headers={**headers, "Content-Type": "application/json"},
                json={"productOrderIds": batch, "quantityClaimCompatibility": True},
            )
            payload = parse_json(response)
            for detail in payload.get("data", []):
                yield _map_record(detail)

    def _access_token(self) -> str:
        timestamp_ms = self._clock_ms()
        response = self._http.request(
            "POST",
            TOKEN_URL,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "client_id": self._client_id,
                "timestamp": timestamp_ms,
                "grant_type": "client_credentials",
                "client_secret_sign": generate_client_secret_sign(
                    self._client_id, self._client_secret, timestamp_ms
                ),
                "type": "SELF",
            },
        )
        payload = parse_json(response)
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise ValueError("Naver token response did not contain an access token")
        return token

    def _changed_product_order_ids(
        self, window: DateWindow, headers: dict[str, str]
    ) -> list[str]:
        params: dict[str, Any] = {
            "lastChangedFrom": _day_start(window.start),
            "lastChangedTo": _day_end(window.end),
            "limitCount": 300,
        }
        ids: list[str] = []
        known_ids: set[str] = set()
        seen_continuations: set[tuple[str, str]] = set()
        while True:
            response = self._http.request("GET", CHANGED_ORDERS_URL, headers=headers, params=params)
            payload = parse_json(response)
            data = payload.get("data") or {}
            for status in data.get("lastChangeStatuses", []):
                product_order_id = status.get("productOrderId")
                if product_order_id is not None:
                    value = str(product_order_id)
                    if value not in known_ids:
                        known_ids.add(value)
                        ids.append(value)

            more = data.get("more")
            if not isinstance(more, dict):
                break
            more_from = more.get("moreFrom")
            more_sequence = more.get("moreSequence")
            if not isinstance(more_from, str) or not isinstance(more_sequence, str):
                break
            continuation = (more_from, more_sequence)
            if continuation in seen_continuations:
                break
            seen_continuations.add(continuation)
            params["lastChangedFrom"] = more_from
            params["moreSequence"] = more_sequence
        return ids


def _map_record(detail: dict[str, Any]) -> ChannelRecord:
    order = detail.get("order") or {}
    product_order = detail.get("productOrder") or {}
    delivery = detail.get("delivery") or {}
    product_order_id = str(product_order["productOrderId"])
    order_status = product_order.get("productOrderStatus")
    delivery_status = delivery.get("deliveryStatus")
    columns = {
        "ProductOrderId": product_order_id,
        "OrderId": _optional_str(order.get("orderId")),
        "ProductId": _optional_str(product_order.get("productId")),
        "OptionId": _optional_str(product_order.get("itemNo")),
        "ProductName": product_order.get("productName"),
        "OptionName": product_order.get("productOption"),
        "Quantity": product_order.get("quantity"),
        "UnitPrice": product_order.get("unitPrice"),
        "TotalPaymentAmount": product_order.get("totalPaymentAmount"),
        "ProductOrderStatus": order_status,
        "ClaimStatus": product_order.get("claimStatus"),
        "DeliveryStatus": delivery_status,
        "PaymentAt": order.get("paymentDate"),
        "DispatchAt": delivery.get("sendDate"),
        "DeliveryCompletedAt": delivery.get("deliveredDate"),
        "DeliveryCompanyCode": delivery.get("deliveryCompany"),
        "TrackingNumber": delivery.get("trackingNumber"),
        "RawOrderStatus": order_status,
        "RawDeliveryStatus": delivery_status,
    }
    raw_json, payload_hash = canonical_payload(detail)
    return ChannelRecord((product_order_id,), columns, raw_json, payload_hash)


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)
