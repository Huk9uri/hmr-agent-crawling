"""Shared channel adapter contracts and inclusive date windows."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, timedelta

from hmr_order_collection.models import ChannelRecord


class InvalidPeriodError(ValueError):
    """An API explicitly rejected a read-only query because its period is too wide."""


def explicit_invalid_period_message(message: object) -> bool:
    """Classify only explicit range-limit messages; never infer from HTTP status."""
    if not isinstance(message, str):
        return False
    normalized = " ".join(message.casefold().split())
    english_range = any(
        marker in normalized for marker in ("date range", "search range", "query range")
    )
    english_width_rejection = any(
        marker in normalized
        for marker in (
            "too long",
            "too wide",
            "exceed maximum",
            "exceeds maximum",
            "maximum width",
            "maximum range",
        )
    )
    korean_range = any(
        marker in normalized
        for marker in (
            "조회기간",
            "조회 기간",
            "검색기간",
            "검색 기간",
            "날짜 범위",
            "일자 범위",
            "조회범위",
            "검색범위",
        )
    )
    korean_width_rejection = any(
        marker in normalized
        for marker in ("초과", "최대 범위", "너무 깁")
    )
    return (english_range and english_width_rejection) or (
        korean_range and korean_width_rejection
    )


@dataclass(frozen=True)
class DateWindow:
    """An inclusive calendar-date interval accepted by a channel API."""

    start: date
    end: date


def iter_windows(start: date, end: date, maximum_days: int) -> Iterator[DateWindow]:
    """Yield adjacent inclusive windows no longer than ``maximum_days``."""
    if maximum_days <= 0:
        raise ValueError("maximum_days must be positive")
    if start > end:
        raise ValueError("start must not be after end")

    current = start
    while current <= end:
        window_end = min(current + timedelta(days=maximum_days - 1), end)
        yield DateWindow(current, window_end)
        current = window_end + timedelta(days=1)


class ChannelAdapter(ABC):
    """Read-only adapter contract implemented by each sales channel."""

    @property
    def pages_fetched(self) -> int:
        """Count successful order-response fetches without retaining response data."""
        return getattr(self, "_page_count", 0)

    def _record_page(self) -> None:
        self._page_count = self.pages_fetched + 1

    @abstractmethod
    def fetch(self, window: DateWindow) -> Iterator[ChannelRecord]:
        """Return every item in an inclusive channel date window."""
        raise NotImplementedError
