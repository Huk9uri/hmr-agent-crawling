"""Read-only SSG.COM shipping-direction order collector."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from hmr_order_collection.channels.base import ChannelAdapter, DateWindow
from hmr_order_collection.config import AppConfig
from hmr_order_collection.http import HttpClient, parse_json
from hmr_order_collection.masking import canonical_payload
from hmr_order_collection.models import ChannelRecord


SSG_ORDERS_URL = "https://eapi.ssgadm.com/api/pd/1/listShppDirection.ssg"
SSG_NON_DELIVERY_URL = "https://eapi.ssgadm.com/api/pd/1/listNonDelivery.ssg"
SSG_DELIVERY_END_URL = "https://eapi.ssgadm.com/api/pd/1/listDeliveryEnd.ssg"
_PRIVATE_FIELDS = frozenset(
    {
        "mbrId",
        "mbrLoginId",
        "ordMemoCntt",
        "ordShpplocId",
        "ordpeHpno",
        "ordpeNm",
        "ordpeRoadAddr",
        "pCus",
        "rcptpeHpno",
        "rcptpeNm",
        "rcptpeTelno",
        "shpplocAddr",
        "shpplocBascAddr",
        "shpplocDtlAddr",
        "shpplocOldZipcd",
        "shpplocZipcd",
    }
)


class SsgAdapter(ChannelAdapter):
    """Collect SSG shipping directions by order-completion date."""

    def __init__(self, config: AppConfig, *, http: HttpClient | None = None) -> None:
        self._api_key = config.require("SSG_API_KEY")
        self._http = http or HttpClient()

    def fetch(self, window: DateWindow) -> Iterator[ChannelRecord]:
        inclusive_days = (window.end - window.start).days + 1
        if inclusive_days < 1 or inclusive_days > 180:
            raise ValueError("SSG order windows must contain between 1 and 180 days")

        request_headers = {
            "Accept": "application/json",
            "Authorization": self._api_key,
            "Content-Type": "application/json",
        }
        response = self._http.request(
            "POST",
            SSG_ORDERS_URL,
            headers=request_headers,
            json={
                "requestShppDirection": {
                    "perdType": "02",
                    "perdStrDts": window.start.isoformat(),
                    "perdEndDts": window.end.isoformat(),
                }
            },
        )
        directions = _result(self, response)
        merged = {_identity(row): dict(row) for row in _shipping_directions(directions.get("shppDirections"))}
        stages = (
            (SSG_NON_DELIVERY_URL, "requestNonDelivery", "nonDeliverys"),
            (SSG_DELIVERY_END_URL, "requestDeliveryEnd", "deliveryEnds"),
        )
        shipping_numbers = dict.fromkeys(identity[2] for identity in merged)
        for shipping_number in shipping_numbers:
            for url, envelope, list_key in stages:
                stage_response = self._http.request(
                    "POST", url, headers=dict(request_headers),
                    json={
                        envelope: {
                            "commType": "02",
                            "commValue": shipping_number,
                        }
                    },
                )
                result = _result(self, stage_response)
                for stage_row in _stage_rows(result.get(list_key), list_key):
                    identity = _identity(stage_row)
                    if identity in merged:
                        merged[identity].update(stage_row)
        for row in merged.values():
            yield _map_record(row)


def _result(adapter: SsgAdapter, response: Any) -> dict[str, Any]:
    adapter._record_page()
    payload = parse_json(response)
    if not isinstance(payload, dict):
        raise ValueError("SSG order response must be a JSON object")
    result = payload.get("result") if isinstance(payload.get("result"), dict) else payload
    if result.get("resultCode") != "00":
        raise ValueError("SSG order response reported a business failure")
    return result


def _identity(row: dict[str, Any]) -> tuple[str, str, str, str]:
    try:
        values = (row["ordNo"], row["ordItemSeq"], row["shppNo"], row["shppSeq"])
    except KeyError as error:
        raise ValueError("SSG row lacked order/shipping identity") from error
    if any(value is None or value == "" for value in values):
        raise ValueError("SSG row lacked order/shipping identity")
    return tuple(str(value) for value in values)


def _stage_rows(value: Any, name: str) -> list[dict[str, Any]]:
    if value is None or value == "":
        return []
    rows = value if isinstance(value, list) else [value]
    rows = [row for row in rows if not (isinstance(row, str) and not row.strip())]
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError(f"SSG {name} list was malformed")
    return rows


def _shipping_directions(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    candidates = value if isinstance(value, list) else [value]
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        if isinstance(candidate, str) and not candidate.strip():
            continue
        if not isinstance(candidate, dict):
            raise ValueError("SSG shipping-direction list was malformed")
        nested = candidate.get("shppDirection", candidate)
        nested_rows = nested if isinstance(nested, list) else [nested]
        if any(not isinstance(row, dict) for row in nested_rows):
            raise ValueError("SSG shipping-direction row was malformed")
        rows.extend(nested_rows)
    return rows


def _map_record(row: dict[str, Any]) -> ChannelRecord:
    identity = _identity(row)
    order_status = _optional_str(row.get("ordStatCd"))
    shipping_status = _optional_str(row.get("shppStatCd"))
    shipping_progress = _optional_str(
        row.get("lastShppProgStatDtlCd") or row.get("shppProgStatDtlCd")
    )
    columns = {
        "OrdNo": identity[0],
        "OrdItemSeq": identity[1],
        "ShppNo": identity[2],
        "ShppSeq": identity[3],
        "SiteNo": _optional_str(row.get("siteNo")),
        "ItemId": _optional_str(row.get("itemId")),
        "UitemId": _optional_str(row.get("uitemId")),
        "SplVenItemId": _optional_str(row.get("splVenItemId")),
        "USplVenItemId": _optional_str(row.get("uSplVenItemId")),
        "ItemName": row.get("itemNm"),
        "UnitItemName": row.get("uitemNm"),
        "OrderQuantity": _integer(row.get("ordQty")),
        "DirectedQuantity": _integer(row.get("dircItemQty")),
        "CanceledQuantity": _integer(row.get("cnclItemQty")),
        "SupplyPrice": _decimal(row.get("splprc")),
        "SalesPrice": _decimal(row.get("sellprc")),
        "RealOrderAmount": _decimal(row.get("rlordAmt")),
        "DiscountAmount": _decimal(row.get("dcAmt")),
        "OrderStatusCode": order_status,
        "ShippingStatusCode": shipping_status,
        "ShippingProgressDetailCode": shipping_progress,
        "OrderReceivedAt": row.get("ordRcpDts"),
        "OrderCompletedAt": row.get("ordCmplDts"),
        "ScheduledShippingDate": _date_value(row.get("shppRsvtDt")),
        "WarehouseOutCompletedAt": row.get("whoutDt"),
        "DeliveryCompanyCode": _optional_str(row.get("delicoVenId")),
        "TrackingNumber": _optional_str(row.get("wblNo")),
        "DeliveryTrackingStatusAt": None,
        "DeliveryCompletedAt": row.get("shppDt"),
        "RawOrderStatus": order_status,
        "RawDeliveryStatus": shipping_progress or shipping_status,
    }
    raw_json, payload_hash = canonical_payload(_mask_private_fields(row))
    return ChannelRecord(identity, columns, raw_json, payload_hash)


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
        raise ValueError("SSG numeric field was invalid") from error


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError("SSG numeric field was invalid") from error


def _date_value(value: Any) -> str | None:
    if value is None or value == "":
        return None
    raw = str(value)
    if len(raw) == 8 and raw.isdigit():
        raw = f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError as error:
        raise ValueError("SSG date field was invalid") from error
