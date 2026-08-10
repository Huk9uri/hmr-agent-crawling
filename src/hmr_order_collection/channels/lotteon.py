"""Read-only LotteON delivery-order collector."""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal, InvalidOperation
from typing import Any

from hmr_order_collection.channels.base import ChannelAdapter, DateWindow
from hmr_order_collection.config import AppConfig
from hmr_order_collection.http import HttpClient, parse_json
from hmr_order_collection.masking import canonical_payload
from hmr_order_collection.models import ChannelRecord


DELIVERY_ORDERS_URL = "https://openapi.lotteon.com/v1/openapi/delivery/v1/SellerDeliveryOrdersSearch"
DELIVERY_PROGRESS_URL = "https://openapi.lotteon.com/v1/openapi/delivery/v1/SellerDeliveryProgressStateSearch"
_PRIVATE_FIELDS = frozenset(
    {
        "odrNm",
        "mphnNo",
        "telNo",
        "emlAddr",
        "dvpCustNm",
        "dvpEmlAddr",
        "dvpTelNo",
        "dvpMphnNo",
        "sftNo",
        "dvpZipNo",
        "dvpJbZipAddr",
        "dvpJbDtlAddr",
        "dvpStnmZipAddr",
        "dvpStnmDtlAddr",
        "indvCstmPclrNo",
        "dvMsg",
        "jntFtdrPwd",
    }
)


class LotteonAdapter(ChannelAdapter):
    """Join LotteON delivery orders and delivery progress without changing state."""

    def __init__(self, config: AppConfig, *, http: HttpClient | None = None) -> None:
        self._api_key = config.require("LOTTEON_API_KEY")
        self._http = http or HttpClient()

    def fetch(self, window: DateWindow) -> Iterator[ChannelRecord]:
        if window.start != window.end:
            raise ValueError("LotteON delivery search windows must be at most 1 day")
        body = {
            "srchStrtDt": f"{window.start:%Y%m%d}000000",
            "srchEndDt": f"{window.end:%Y%m%d}235959",
        }
        headers = {
            "Accept": "application/json",
            "Accept-Language": "ko",
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "X-Timezone": "GMT+09:00",
        }
        orders = self._list(DELIVERY_ORDERS_URL, body, headers, "deliveryOrderList")
        progress_rows = self._list(
            DELIVERY_PROGRESS_URL, body, headers, "deliveryProgressStateList"
        )
        progress_by_identity: dict[tuple[str, str], dict[str, Any]] = {}
        for progress in progress_rows:
            identity = _identity(progress)
            previous = progress_by_identity.get(identity)
            if previous is None or str(progress.get("dvTrcStatDttm") or "") >= str(
                previous.get("dvTrcStatDttm") or ""
            ):
                progress_by_identity[identity] = progress
        for order in orders:
            yield _map_record(order, progress_by_identity.get(_identity(order)))

    def _list(
        self,
        url: str,
        body: dict[str, str],
        headers: dict[str, str],
        list_key: str,
    ) -> list[dict[str, Any]]:
        response = self._http.request("POST", url, headers=dict(headers), json=dict(body))
        payload = parse_json(response)
        if not isinstance(payload, dict):
            raise ValueError("LotteON response must be a JSON object")
        if payload.get("returnCode") not in {"0000", "SUCCESS"}:
            raise ValueError("LotteON response reported a business failure")
        data = payload.get("data")
        if data is None:
            return []
        if not isinstance(data, dict):
            raise ValueError("LotteON response data must be an object")
        rows = data.get(list_key) or []
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError("LotteON response list was malformed")
        return rows


def _identity(row: dict[str, Any]) -> tuple[str, str]:
    try:
        return str(row["odNo"]), str(row["odSeq"])
    except KeyError as error:
        raise ValueError("LotteON row lacked order/item identity") from error


def _map_record(order: dict[str, Any], progress: dict[str, Any] | None) -> ChannelRecord:
    order_no, order_item_seq = _identity(order)
    progress = progress or {}
    order_status = _optional_str(order.get("odPrgsStepCd"))
    delivery_status = _optional_str(progress.get("odPrgsStepCd")) or order_status
    progress_time = progress.get("dvTrcStatDttm")
    columns = {
        "OrderNo": order_no,
        "OrderItemSeq": order_item_seq,
        "ProductId": _optional_str(order.get("spdNo") or order.get("pdNo")),
        "OptionId": _optional_str(order.get("sitmNo") or order.get("itmNo")),
        "ProductName": order.get("spdNm") or order.get("pdNm"),
        "OptionName": order.get("sitmNm") or order.get("itmNm"),
        "Quantity": _integer(order.get("odQty")),
        "CanceledQuantity": _integer(order.get("cnclQty")),
        "SalesAmount": _decimal(order.get("slAmt")),
        "PaymentAmount": _decimal(order.get("actualAmt")),
        "OrderStatus": order_status,
        "DeliveryStatus": delivery_status,
        "OrderedAt": order.get("odCmptDttm"),
        "PaidAt": order.get("payDttm"),
        "DispatchedAt": progress.get("owhoDttm") or order.get("owhoDttm"),
        "DeliveryCompletedAt": progress_time if delivery_status in {"14", "15"} else None,
        "DeliveryCompanyCode": _optional_str(progress.get("dvCoCd") or order.get("dvCoCd")),
        "TrackingNumber": _optional_str(progress.get("invcNo") or order.get("invcNo")),
        "RawOrderStatus": order_status,
        "RawDeliveryStatus": delivery_status,
    }
    raw_json, payload_hash = canonical_payload(
        _mask_private_fields({"deliveryOrder": order, "deliveryProgress": progress})
    )
    return ChannelRecord((order_no, order_item_seq), columns, raw_json, payload_hash)


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
    return None if value is None or value == "" else int(Decimal(str(value)))


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError("LotteON numeric field was invalid") from error
