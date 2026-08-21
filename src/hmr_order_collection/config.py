"""Strict, non-logging configuration loading."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from types import MappingProxyType
from typing import Mapping


_ENV_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


class ConfigurationError(ValueError):
    """Raised when a configuration file cannot be parsed safely."""


@dataclass(frozen=True)
class AppConfig:
    """Immutable values read from a single dotenv file."""

    values: Mapping[str, str]

    def get(self, key: str, default: str | None = None) -> str | None:
        return self.values.get(key, default)

    def require(self, key: str) -> str:
        value = self.values.get(key)
        if value is None or not value:
            raise ConfigurationError(f"Missing required configuration: {key}")
        return value

    def orchestrator_max_workers(self, channel_count: int) -> int:
        message = "ORCHESTRATOR_MAX_WORKERS must be an integer between 1 and the channel count"
        raw_value = self.values.get("ORCHESTRATOR_MAX_WORKERS", "4")
        try:
            value = int(raw_value)
        except (TypeError, ValueError) as error:
            raise ConfigurationError(message) from error
        if not 1 <= value <= channel_count:
            raise ConfigurationError(message)
        return value


def _parse_value(raw_value: str, line_number: int) -> str:
    value = raw_value.strip()
    if not value:
        return ""
    if value[0] in {"'", '"'}:
        quote = value[0]
        if len(value) < 2 or value[-1] != quote:
            raise ConfigurationError(f"Unterminated quoted value on line {line_number}")
        return value[1:-1]
    if value.startswith("'") or value.startswith('"'):
        raise ConfigurationError(f"Invalid quoted value on line {line_number}")
    return value


def load_config(path: Path) -> AppConfig:
    """Load KEY=VALUE entries, rejecting malformed and duplicate definitions."""
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ConfigurationError(f"Cannot read configuration file: {path}") from error

    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in line:
            raise ConfigurationError(f"Expected KEY=VALUE on line {line_number}")
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not _ENV_KEY.fullmatch(key):
            raise ConfigurationError(f"Invalid configuration key on line {line_number}")
        if key in values:
            raise ConfigurationError(f"Duplicate configuration key on line {line_number}")
        values[key] = _parse_value(raw_value, line_number)

    return AppConfig(MappingProxyType(values))
