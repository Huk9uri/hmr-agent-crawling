"""Immutable shared collector contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True)
class ChannelRecord:
    """One masked source order item ready for history persistence."""

    identity: tuple
    columns: Mapping[str, Any]
    raw_json: str
    payload_hash: bytes

    def __post_init__(self) -> None:
        object.__setattr__(self, "columns", MappingProxyType(dict(self.columns)))
