"""Bounded, read-only HTTP helpers that never expose response bodies in errors."""

from __future__ import annotations

from collections.abc import Callable
import re
import time
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from xml.etree import ElementTree

import requests


CONNECT_TIMEOUT_SECONDS = 10
READ_TIMEOUT_SECONDS = 60
DEFAULT_TIMEOUT = (CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS)
RETRYABLE_STATUS_CODES = frozenset({429})
_XML_DECLARED_ENCODING = re.compile(
    br"^\s*<\?xml\s+[^>]*\bencoding\s*=\s*['\"]"
    br"(?P<encoding>[A-Za-z][A-Za-z0-9._-]*)['\"]",
    re.IGNORECASE,
)


class HttpResponseError(RuntimeError):
    """An HTTP or response-decoding failure with no response-body detail."""


def _safe_url(url: str) -> str:
    parts = urlsplit(url)
    host = parts.netloc.rsplit("@", 1)[-1]
    return urlunsplit((parts.scheme, host, parts.path, "", ""))


def _is_retryable_status(status_code: int) -> bool:
    return status_code in RETRYABLE_STATUS_CODES or 500 <= status_code <= 599


def parse_json(response: requests.Response) -> Any:
    """Decode JSON while deliberately withholding a malformed response body."""
    try:
        return response.json()
    except ValueError as error:
        raise HttpResponseError(f"Invalid JSON response from {_safe_url(response.url)}") from error


def parse_xml(response: requests.Response) -> ElementTree.Element:
    """Decode XML while deliberately withholding a malformed response body."""
    try:
        content = response.content
        declaration = _XML_DECLARED_ENCODING.match(content)
        if declaration is not None:
            encoding = declaration.group("encoding").decode("ascii")
            content = content.decode(encoding)
        return ElementTree.fromstring(content)
    except (ElementTree.ParseError, LookupError, ValueError) as error:
        raise HttpResponseError(f"Invalid XML response from {_safe_url(response.url)}") from error


class HttpClient:
    """A small requests wrapper with bounded retry and safe error messages."""

    def __init__(
        self,
        session: requests.Session | None = None,
        max_attempts: int = 3,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self._session = session or requests.Session()
        self._max_attempts = max_attempts
        self._sleep = sleep

    def request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
        for attempt in range(1, self._max_attempts + 1):
            try:
                response = self._session.request(method, url, **kwargs)
            except requests.RequestException as error:
                if attempt == self._max_attempts:
                    raise HttpResponseError(
                        f"Request failed for {method.upper()} {_safe_url(url)}"
                    ) from None
                self._sleep(attempt)
                continue
            if _is_retryable_status(response.status_code) and attempt < self._max_attempts:
                self._sleep(attempt)
                continue
            if response.status_code >= 400:
                raise HttpResponseError(
                    f"HTTP {response.status_code} for {method.upper()} {_safe_url(url)}"
                )
            return response
        raise AssertionError("unreachable")

    def get_json(self, url: str, **kwargs: Any) -> Any:
        response = self.request("GET", url, **kwargs)
        return parse_json(response)

    def get_xml(self, url: str, **kwargs: Any) -> ElementTree.Element:
        return parse_xml(self.request("GET", url, **kwargs))
