"""Test package configuration for the source-layout project."""

import sys
from pathlib import Path


_SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(_SOURCE_ROOT))
