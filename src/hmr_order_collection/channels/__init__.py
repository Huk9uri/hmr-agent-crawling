"""Strict registry for every supported channel adapter."""

from __future__ import annotations

from hmr_order_collection.channels.base import ChannelAdapter
from hmr_order_collection.channels.cj_onstyle import CjOnstyleAdapter
from hmr_order_collection.channels.coupang import CoupangAdapter
from hmr_order_collection.channels.elevenst import ElevenstAdapter
from hmr_order_collection.channels.godomall import GodomallAdapter
from hmr_order_collection.channels.lotteon import LotteonAdapter
from hmr_order_collection.channels.naver import NaverAdapter
from hmr_order_collection.channels.ssg import SsgAdapter
from hmr_order_collection.channels.toss import TossShoppingAdapter
from hmr_order_collection.config import AppConfig


CHANNEL_NAMES = (
    "naver",
    "coupang",
    "godomall",
    "lotteon",
    "elevenst",
    "ssg",
    "cj_onstyle",
    "toss",
)

# Inclusive limits used for splitting requests and the initial maximum-window run.
# Conservative one-day values remain in force where the live boundary probe is deferred.
MAXIMUM_WINDOW_DAYS = {
    "naver": 1,
    "coupang": 31,
    "godomall": 1,
    "lotteon": 1,
    "elevenst": 1,
    "ssg": 180,
    "cj_onstyle": 31,
    "toss": 31,
}

# Highest read-only candidate attempted by --probe-boundaries. LotteON's
# documented one-day limit is never exceeded.
BOUNDARY_PROBE_START_DAYS = {
    "godomall": 31,
    "lotteon": 1,
    "elevenst": 7,
}


def build_adapter_registry(config: AppConfig) -> dict[str, ChannelAdapter]:
    """Instantiate every adapter, failing if any channel credential is absent."""
    return {
        "naver": NaverAdapter(config),
        "coupang": CoupangAdapter(config),
        "godomall": GodomallAdapter(config),
        "lotteon": LotteonAdapter(config),
        "elevenst": ElevenstAdapter(config),
        "ssg": SsgAdapter(config),
        "cj_onstyle": CjOnstyleAdapter(config),
        "toss": TossShoppingAdapter(config),
    }
