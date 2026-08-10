"""PII-safe masking and stable payload serialization."""

from __future__ import annotations

import hashlib
import json
import re


_SENSITIVE_PARTS = frozenset(
    {"name", "phone", "tel", "address", "email", "customs", "token", "secret", "key"}
)
_PRODUCT_OR_ORDER_IDENTIFIER = re.compile(r"(?:order|product)[_-]?(?:id|no|number|code|seq|sno)\Z", re.IGNORECASE)
_PRODUCT_NAME = re.compile(r"product[_-]?name\Z", re.IGNORECASE)
_KEY_PARTS = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|[^A-Za-z0-9]+")


def _is_sensitive_key(key: object) -> bool:
    if (
        not isinstance(key, str)
        or _PRODUCT_OR_ORDER_IDENTIFIER.search(key)
        or _PRODUCT_NAME.search(key)
    ):
        return False
    parts = {part.lower() for part in _KEY_PARTS.split(key) if part}
    return bool(parts & _SENSITIVE_PARTS)


def mask_payload(value: object) -> object:
    """Recursively replace values associated with sensitive field names."""
    if isinstance(value, dict):
        return {
            key: "***" if _is_sensitive_key(key) else mask_payload(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [mask_payload(item) for item in value]
    if isinstance(value, tuple):
        return tuple(mask_payload(item) for item in value)
    return value


def canonical_payload(value: object) -> tuple[str, bytes]:
    """Return compact, sorted masked JSON and its SHA-256 digest."""
    raw_json = json.dumps(
        mask_payload(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return raw_json, hashlib.sha256(raw_json.encode("utf-8")).digest()
