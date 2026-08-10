"""Read-only 11st XML order collector."""

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


BASE_URL = "https://api.11st.co.kr/rest/ordservices"
ORDER_ENDPOINTS = tuple(
    f"{BASE_URL}/{state}" for state in ("complete", "packing", "shipping", "delivered")
)
_PRIVATE_FIELDS = frozenset(
    {
        "ordId",
        "ordNm",
        "ordEmail",
        "ordMailNo",
        "ordPrtblTel",
        "ordTel",
        "ordererName",
        "ordererEmail",
        "ordererPhone",
        "rcvrNm",
        "rcvrPrtblNo",
        "rcvrPrtblTel",
        "rcvrTel",
        "rcvrMailNo",
        "rcvrBaseAddr",
        "rcvrDtlsAddr",
        "receiverName",
        "receiverEmail",
        "receiverPhone",
        "receiverAddress",
        "customsCode",
    }
)


class ElevenstAdapter(ChannelAdapter):
    """Collect all read-only 11st order states as namespaced XML."""

    def __init__(self, config: AppConfig, *, http: HttpClient | None = None) -> None:
        self._api_key = config.require("ELEVENST_API_KEY")
        self._http = http or HttpClient()

    def fetch(self, window: DateWindow) -> Iterator[ChannelRecord]:
        start = window.start.strftime("%Y%m%d")
        end = window.end.strftime("%Y%m%d")
        headers = {"Accept": "application/xml", "openapikey": self._api_key}
        seen: set[tuple[str, str]] = set()
        for endpoint in ORDER_ENDPOINTS:
            response = self._http.request(
                "GET", f"{endpoint}/{start}/{end}", headers=dict(headers)
            )
            root = parse_xml(response)
            _raise_for_business_error(root)
            for order_element, product_element in _order_products(root):
                record = _map_record(order_element, product_element)
                if record.identity not in seen:
                    seen.add(record.identity)
                    yield record


def _raise_for_business_error(root: ElementTree.Element) -> None:
    code = _first_text(root, ("resultCode", "code"))
    if code is not None and code not in {"0", "000", "0000", "200", "SUCCESS"}:
        raise ValueError("11st order response reported a business failure")


def _order_products(
    root: ElementTree.Element,
) -> Iterator[tuple[ElementTree.Element, ElementTree.Element]]:
    parents = {child: parent for parent in root.iter() for child in parent}
    for element in root.iter():
        if _direct_text(element, "orderProductNo") is None:
            continue
        order_element = element
        current = element
        while _direct_text(order_element, "orderNo") is None and current in parents:
            current = parents[current]
            order_element = current
        yield order_element, element


def _map_record(
    order_element: ElementTree.Element, product_element: ElementTree.Element
) -> ChannelRecord:
    order = _xml_value(order_element)
    product = _xml_value(product_element)
    if not isinstance(order, dict) or not isinstance(product, dict):
        raise ValueError("11st order XML row was malformed")
    order_no = _required(_direct_text(order_element, "orderNo"), "orderNo")
    order_product_no = _required(
        _direct_text(product_element, "orderProductNo"), "orderProductNo"
    )
    order_status = _first_value(product, order, names=("orderStatus", "orderStatusType"))
    delivery_status = _first_value(
        product, order, names=("deliveryStatus", "deliveryStatusType")
    )
    columns = {
        "OrderNo": order_no,
        "OrderProductNo": order_product_no,
        "ProductId": _optional_str(_first_value(product, names=("productNo", "sellerProductNo"))),
        "OptionId": _optional_str(_first_value(product, names=("optionNo", "productOptionNo"))),
        "ProductName": _first_value(product, names=("productName",)),
        "OptionName": _first_value(product, names=("optionName", "productOption")),
        "Quantity": _integer(_first_value(product, names=("quantity", "orderQuantity", "buyQuantity"))),
        "OrderAmount": _decimal(_first_value(product, names=("orderAmount", "payAmount", "salePrice"))),
        "OrderStatus": _optional_str(order_status),
        "DeliveryStatus": _optional_str(delivery_status),
        "OrderedAt": _first_value(product, order, names=("orderDate", "orderedAt")),
        "PaidAt": _first_value(product, order, names=("paymentDate", "paidAt")),
        "DispatchedAt": _first_value(product, order, names=("dispatchDate", "deliveryStartDate")),
        "DeliveryCompanyCode": _optional_str(_first_value(product, order, names=("deliveryCompanyCode", "deliveryCompany"))),
        "TrackingNumber": _optional_str(_first_value(product, order, names=("invoiceNo", "trackingNumber"))),
        "RawOrderStatus": _optional_str(order_status),
        "RawDeliveryStatus": _optional_str(delivery_status),
    }
    raw_json, payload_hash = canonical_payload(
        _mask_private_fields({"order": order, "orderProduct": product})
    )
    return ChannelRecord((order_no, order_product_no), columns, raw_json, payload_hash)


def _mask_private_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "***" if key in _PRIVATE_FIELDS else _mask_private_fields(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_mask_private_fields(item) for item in value]
    return value


def _first_value(*values: dict[str, Any], names: tuple[str, ...]) -> Any:
    for name in names:
        for value in values:
            candidate = value.get(name)
            if candidate is not None and candidate != "":
                return candidate
    return None


def _xml_value(element: ElementTree.Element) -> Any:
    children = list(element)
    if not children:
        return None if element.text is None or not element.text.strip() else element.text.strip()
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


def _direct_text(element: ElementTree.Element, name: str) -> str | None:
    child = next((item for item in element if _local_name(item.tag) == name), None)
    if child is None or child.text is None or not child.text.strip():
        return None
    return child.text.strip()


def _first_text(root: ElementTree.Element, names: tuple[str, ...]) -> str | None:
    for element in root.iter():
        if _local_name(element.tag) in names and element.text and element.text.strip():
            return element.text.strip()
    return None


def _required(value: Any, name: str) -> str:
    if value is None or value == "":
        raise ValueError(f"11st order item did not contain {name}")
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
        raise ValueError("11st numeric field was invalid") from error
