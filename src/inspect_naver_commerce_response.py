import base64
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bcrypt
import requests
from dotenv import load_dotenv


ENV_PATH = Path(r"C:\workspace\HMR_Agent_Crawling\.env")
BASE_URL = "https://api.commerce.naver.com/external"
SAFE_VALUE_FIELDS = {
    "productOrderStatus",
    "placeOrderStatus",
    "deliveryStatus",
    "deliveryMethod",
    "lastChangedType",
    "claimType",
    "claimStatus",
}


def type_name(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def collect_schema(value, path="$", output=None):
    output = output if output is not None else {}
    output[path] = type_name(value)
    if isinstance(value, dict):
        for key, child in value.items():
            collect_schema(child, f"{path}.{key}", output)
    elif isinstance(value, list):
        for child in value[:10]:
            collect_schema(child, f"{path}[]", output)
    return output


def safe_status_values(value, output=None):
    output = output if output is not None else {}
    if isinstance(value, dict):
        for key, child in value.items():
            if key in SAFE_VALUE_FIELDS and child is not None:
                output.setdefault(key, set()).add(str(child))
            safe_status_values(child, output)
    elif isinstance(value, list):
        for child in value:
            safe_status_values(child, output)
    return {key: sorted(values) for key, values in output.items()}


def build_signature(client_id, client_secret, timestamp):
    password = f"{client_id}_{timestamp}".encode("utf-8")
    hashed = bcrypt.hashpw(password, client_secret.encode("utf-8"))
    return base64.b64encode(hashed).decode("utf-8")


def request_json(method, url, **kwargs):
    response = requests.request(method, url, timeout=30, **kwargs)
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if not response.ok:
        code = payload.get("code") if isinstance(payload, dict) else None
        message = payload.get("message") if isinstance(payload, dict) else None
        raise RuntimeError(
            f"HTTP {response.status_code}; code={code}; message={message}"
        )
    return response.status_code, payload


def main():
    load_dotenv(ENV_PATH, override=False)
    client_id = os.getenv("NAVER_COMMERCE_CLIENT_ID")
    client_secret = os.getenv("NAVER_COMMERCE_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError("Commerce API credentials are not configured")

    timestamp = int(time.time() * 1000)
    token_status, token_payload = request_json(
        "POST",
        f"{BASE_URL}/v1/oauth2/token",
        data={
            "client_id": client_id,
            "timestamp": timestamp,
            "client_secret_sign": build_signature(
                client_id, client_secret, timestamp
            ),
            "grant_type": "client_credentials",
            "type": "SELF",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    access_token = token_payload.get("access_token")
    if not access_token:
        raise RuntimeError("OAuth response did not contain an access token")

    kst = timezone(timedelta(hours=9))
    changed_from = (datetime.now(kst) - timedelta(hours=24)).isoformat(
        timespec="milliseconds"
    )
    changed_status, changed_payload = request_json(
        "GET",
        f"{BASE_URL}/v1/pay-order/seller/product-orders/last-changed-statuses",
        params={"lastChangedFrom": changed_from, "limitCount": 100},
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
        },
    )

    statuses = (
        changed_payload.get("data", {}).get("lastChangeStatuses", [])
        if isinstance(changed_payload, dict)
        else []
    )
    output = {
        "oauth_http_status": token_status,
        "changed_orders_http_status": changed_status,
        "changed_order_count": len(statuses),
        "changed_orders_schema": collect_schema(changed_payload),
        "changed_orders_safe_values": safe_status_values(changed_payload),
    }

    selected_by_status = {}
    for item in statuses:
        if not isinstance(item, dict) or not item.get("productOrderId"):
            continue
        status = item.get("productOrderStatus", "UNKNOWN")
        selected_by_status.setdefault(status, item["productOrderId"])
    product_order_ids = list(selected_by_status.values())[:10]
    if product_order_ids:
        detail_status, detail_payload = request_json(
            "POST",
            f"{BASE_URL}/v1/pay-order/seller/product-orders/query",
            json={
                "productOrderIds": product_order_ids,
                "quantityClaimCompatibility": True,
            },
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {access_token}",
            },
        )
        output.update(
            {
                "detail_http_status": detail_status,
                "detail_sample_count": len(
                    detail_payload.get("data", [])
                    if isinstance(detail_payload, dict)
                    else []
                ),
                "detail_schema": collect_schema(detail_payload),
                "detail_safe_values": safe_status_values(detail_payload),
            }
        )
    else:
        output["detail_note"] = "최근 24시간 변경 주문이 없어 상세 조회를 생략함"

    access_token = None
    client_id = None
    client_secret = None
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
