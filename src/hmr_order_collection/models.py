"""Immutable shared collector contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ChannelRecord:
    """One masked source order item ready for history persistence."""

    identity: tuple
    columns: dict[str, Any]
    raw_json: str
    payload_hash: bytes
