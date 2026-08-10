"""Read-only Toss Shopping order collector."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from decimal import Decimal, InvalidOperation
import time
from typing import Any

from hmr_order_collection.channels.base import ChannelAdapter, DateWindow
from hmr_order_collection.config import AppConfig
from hmr_order_collection.http import HttpClient, parse_json
from hmr_order_collection.masking import canonical_payload
from hmr_order_collection.models import ChannelRecord


TOKEN_URL = "https://oauth2.cert.toss.im/token"
ORDERS_URL = "https://shopping-fep.toss.im/api/v3/shopping-fep/orders/v2"
TOKEN_SCOPE = "toss-shopping-fep:write"
TOKEN_REFRESH_MARGIN_SECONDS = 30
_PRIVATE_FIELDS = frozenset(
    {
        "address",
        "detailAddress",
        "ordererName",
        "ordererPhone",
        "ordererRealPhone",
        "receiverName",
        "receiverPhone",
        "receiverRealPhone",
        "shippingNote",
        "zipCode",
    }
)


class TossShoppingAdapter(ChannelAdapter):
    """Collect Toss Shopping order products with cached OAuth credentials."""

    def __init__(
        self,
        config: AppConfig,
        *,
        http: HttpClient | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._access_key = config.require("TOSS_SHOPPING_ACCESS_KEY")
        self._secret_key = config.require("TOSS_SHOPPING_SECRET_KEY")
        self._http = http or HttpClient()
        self._clock = clock or time.monotonic
        self._token: str | None = None
        self._refresh_at = 0.0

    def fetch(self, window: DateWindow) -> Iterator[ChannelRecord]:
        inclusive_days = (window.end - window.start).days + 1
        if inclusive_days < 1 or inclusive_days > 31:
            raise ValueError("Toss Shopping order windows must contain between 1 and 31 days")

        token = self._access_token()
        headers = {"Accept": "application/json", "Authorization": f"Bearer {token}"}
        params: dict[str, Any] = {
            "startDate": window.start.isoformat(),
            "endDate": window.end.isoformat(),
            "limit": 50,
        }
        seen_cursors: set[str] = set()
        while True:
            response = self._http.request(
                "GET", ORDERS_URL, headers=dict(headers), params=dict(params)
            )
            payload = parse_json(response)
            if not isinstance(payload, dict):
                raise ValueError("Toss Shopping order response must be a JSON object")
            if payload.get("resultType") != "SUCCESS":
                raise ValueError("Toss Shopping order response reported a business failure")
            success = payload.get("success")
            if not isinstance(success, dict):
                raise ValueError("Toss Shopping success response was malformed")
            results = success.get("results") or []
            if not isinstance(results, list) or any(not isinstance(row, dict) for row in results):
                raise ValueError("Toss Shopping order list was malformed")
            for row in results:
                yield _map_record(row)

            next_cursor = success.get("nextCursor")
            if next_cursor is None:
                break
            if not isinstance(next_cursor, str) or not next_cursor:
                raise ValueError("Toss Shopping nextCursor was malformed")
            if next_cursor in seen_cursors:
                raise ValueError("Toss Shopping returned a repeated nextCursor")
            seen_cursors.add(next_cursor)
            params["nextCursor"] = next_cursor

    def _access_token(self) -> str:
        now = self._clock()
        if self._token is not None and now < self._refresh_at:
            return self._token
        response = self._http.request(
            "POST",
            TOKEN_URL,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "client_credentials",
                "client_id": self._access_key,
                "client_secret": self._secret_key,
                "scope": TOKEN_SCOPE,
            },
        )
        payload = parse_json(response)
        if not isinstance(payload, dict):
            raise ValueError("Toss Shopping token response must be a JSON object")
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise ValueError("Toss Shopping token response lacked an access token")
        expires_in = payload.get("expires_in")
        try:
            lifetime = float(expires_in)
        except (TypeError, ValueError) as error:
            raise ValueError("Toss Shopping token response had an invalid expiry") from error
        if lifetime <= 0:
            raise ValueError("Toss Shopping token response had an invalid expiry")
        refresh_margin = min(TOKEN_REFRESH_MARGIN_SECONDS, lifetime / 2)
        self._token = token
        self._refresh_at = now + lifetime - refresh_margin
        return token


def _map_record(row: dict[str, Any]) -> ChannelRecord:
    try:
        order_id = int(row["orderId"])
        order_product_id = int(row["orderProductId"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Toss Shopping row lacked numeric order identity") from error
    status = _optional_str(row.get("orderProductStatus"))
    columns = {
        "OrderId": order_id,
        "OrderProductId": order_product_id,
        "ProductId": _integer(row.get("productId")),
        "StockId": _integer(row.get("stockId")),
        "ProductName": row.get("productName"),
        "OptionName": row.get("optionName"),
        "Quantity": _integer(row.get("quantity")),
        "Price": _integer(row.get("price")),
        "OriginPrice": _integer(row.get("originPrice")),
        "TotalDiscountPrice": _integer(row.get("totalDiscountPrice")),
        "TossShoppingDiscount": _integer(row.get("tossShoppingDiscount")),
        "TossPayDiscount": _integer(row.get("tossPayDiscount")),
        "TossPayPoint": _integer(row.get("tossPayPoint")),
        "OrderProductStatus": status,
        "OrderedAt": row.get("orderedAt"),
        "CanceledAt": row.get("canceledAt"),
        "ConfirmedAt": row.get("confirmedAt"),
        "ShippingDeadlineAt": row.get("shippingDeadlineAt"),
        "DeliveryCompanyCode": _optional_str(row.get("deliveryCompanyCode")),
        "ShippingTrackingNumber": _optional_str(row.get("shippingTrackingNumber")),
        "DeliveryFeeGroupId": _integer(row.get("deliveryFeeGroupId")),
        "DeliveryFee": _integer(row.get("deliveryFee")),
        "DeliveryLocationType": _optional_str(row.get("deliveryLocationType")),
        "NormalDeliveryFee": _integer(row.get("normalDeliveryFee")),
        "JejuDeliveryFee": _integer(row.get("jejuDeliveryFee")),
        "MountainDeliveryFee": _integer(row.get("mountainDeliveryFee")),
        "ProductManagementCode": _optional_str(row.get("productManagementCode")),
        "ProductItemManagementCode": _optional_str(row.get("productItemManagementCode")),
        "RawOrderStatus": status,
        "RawDeliveryStatus": status,
    }
    raw_json, payload_hash = canonical_payload(_mask_private_fields(row))
    return ChannelRecord((order_product_id,), columns, raw_json, payload_hash)


def _mask_private_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "***" if key in _PRIVATE_FIELDS else _mask_private_fields(item)
            for key, item in value.items()
        }
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
        raise ValueError("Toss Shopping numeric field was invalid") from error
