"""Shared channel adapter contracts and inclusive date windows."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, timedelta

from hmr_order_collection.models import ChannelRecord


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

    @abstractmethod
    def fetch(self, window: DateWindow) -> Iterator[ChannelRecord]:
        """Return every item in an inclusive channel date window."""
        raise NotImplementedError
