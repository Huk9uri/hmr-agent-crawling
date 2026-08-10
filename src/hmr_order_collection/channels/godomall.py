"""Read-only NHN Commerce Godomall5 order collector."""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal, InvalidOperation
from typing import Any
from xml.etree import ElementTree

from hmr_order_collection.channels.base import ChannelAdapter, DateWindow
from hmr_order_collection.config import AppConfig
from hmr_order_collection.http import HttpClient, parse_xml
from hmr_order_collection.masking import canonical_payload
from hmr_order_collection.models import ChannelRecord


GODOMALL_ORDER_SEARCH_URL = "https://openhub.godo.co.kr/godomall5/order/Order_Search.php"
PAGE_SIZE = 100


class GodomallAdapter(ChannelAdapter):
    """Collect Godomall5 orders through the read-only Order_Search endpoint."""

    def __init__(self, config: AppConfig, *, http: HttpClient | None = None) -> None:
        self._partner_key = config.require("GODOMALL_PARTNER_KEY")
        self._user_key = config.require("GODOMALL_USER_KEY")
        self._http = http or HttpClient()

    def fetch(self, window: DateWindow) -> Iterator[ChannelRecord]:
        data: dict[str, Any] = {
            "partner_key": self._partner_key,
            "key": self._user_key,
            "dateType": "order",
            "startDate": window.start.isoformat(),
            "endDate": window.end.isoformat(),
            "size": PAGE_SIZE,
        }
        seen_last_orders: set[str] = set()
        seen_items: set[tuple[str, str]] = set()
        while True:
            response = self._http.request(
                "POST",
                GODOMALL_ORDER_SEARCH_URL,
                headers={
                    "Accept": "application/xml",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data=dict(data),
            )
            root = parse_xml(response)
            code = _first_text(root, "code")
            if code not in {None, "000"}:
                raise ValueError("Godomall order response reported a business failure")

            orders = _elements(root, "order_data")
            for order_element in orders:
                for record in _order_records(order_element):
                    if record.identity not in seen_items:
                        seen_items.add(record.identity)
                        yield record

            has_more = (_first_text(root, "lastOrder") or "").lower() == "true"
            if not has_more:
                break
            if not orders:
                raise ValueError("Godomall continuation cursor was missing")
            last_order = _direct_text(orders[-1], "orderNo")
            if not last_order:
                raise ValueError("Godomall continuation cursor was missing")
            if last_order in seen_last_orders:
                raise ValueError("Godomall continuation cursor was repeated")
            seen_last_orders.add(last_order)
            data["lastOrder"] = last_order


def _order_records(order_element: ElementTree.Element) -> Iterator[ChannelRecord]:
    order = _xml_value(order_element)
    if not isinstance(order, dict):
        return
    order_no = _required(order, "orderNo")
    goods_container = _direct_element(order_element, "orderGoodsData")
    if goods_container is None:
        return
    item_elements = [child for child in goods_container if _local_name(child.tag) in {"item", "orderGoodsData"}]
    if not item_elements and _direct_text(goods_container, "sno") is not None:
        item_elements = [goods_container]
    for item_element in item_elements:
        item = _xml_value(item_element)
        if not isinstance(item, dict):
            continue
        item_sno = _required(item, "sno")
        order_status = item.get("orderStatus") or order.get("orderStatus")
        columns = {
            "OrderNo": order_no,
            "OrderItemSno": item_sno,
            "OrderChannelCode": order.get("orderChannelFl"),
            "ExternalOrderNo": _optional_str(order.get("apiOrderNo")),
            "ProductCode": _optional_str(item.get("goodsNo") or item.get("goodsCd")),
            "OptionCode": _optional_str(item.get("optionSno")),
            "ProductName": item.get("goodsNm"),
            "OptionName": item.get("optionInfo") or item.get("optionTextInfo"),
            "Quantity": _integer(item.get("goodsCnt")),
            "UnitPrice": _decimal(item.get("goodsPrice")),
            "PaymentAmount": _decimal(order.get("settlePrice")),
            "DiscountAmount": _decimal(order.get("totalGoodsDcPrice")),
            "DeliveryFee": _decimal(order.get("totalDeliveryCharge")),
            "OrderStatus": order_status,
            "PaymentStatus": order.get("orderStatus"),
            "DeliveryStatus": order_status,
            "OrderedAt": order.get("orderDate"),
            "PaidAt": item.get("paymentDt") or order.get("paymentDt"),
            "DispatchedAt": item.get("deliveryDt"),
            "DeliveryCompanyCode": _optional_str(item.get("invoiceCompanySno")),
            "TrackingNumber": _optional_str(item.get("invoiceNo")),
            "RawOrderStatus": order_status,
            "RawDeliveryStatus": order_status,
        }
        safe_order = dict(order)
        if "orderInfoData" in safe_order:
            safe_order["orderInfoData"] = "***"
        raw_json, payload_hash = canonical_payload(
            {"order": safe_order, "orderItem": item}
        )
        yield ChannelRecord((order_no, item_sno), columns, raw_json, payload_hash)


def _xml_value(element: ElementTree.Element) -> Any:
    children = list(element)
    if not children:
        text = element.text
        return None if text is None or not text.strip() else text.strip()
    result: dict[str, Any] = {}
    for child in children:
        key = _local_name(child.tag)
        value = _xml_value(child)
        if key in result:
            current = result[key]
            result[key] = current + [value] if isinstance(current, list) else [current, value]
        else:
            result[key] = value
    return result


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _elements(root: ElementTree.Element, name: str) -> list[ElementTree.Element]:
    return [element for element in root.iter() if _local_name(element.tag) == name]


def _first_text(root: ElementTree.Element, name: str) -> str | None:
    elements = _elements(root, name)
    return None if not elements else _text(elements[0])


def _direct_element(parent: ElementTree.Element, name: str) -> ElementTree.Element | None:
    return next((child for child in parent if _local_name(child.tag) == name), None)


def _direct_text(parent: ElementTree.Element, name: str) -> str | None:
    child = _direct_element(parent, name)
    return None if child is None else _text(child)


def _text(element: ElementTree.Element) -> str | None:
    return None if element.text is None or not element.text.strip() else element.text.strip()


def _required(values: dict[str, Any], key: str) -> str:
    value = values.get(key)
    if value is None or str(value) == "":
        raise ValueError(f"Godomall order item did not contain {key}")
    return str(value)


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
        raise ValueError("Godomall numeric field was invalid") from error
