"""Render the reviewed channel API field contract for operators."""

from __future__ import annotations

import json
from pathlib import Path


CHANNELS = (
    ("naver", "네이버 스마트스토어"),
    ("toss", "토스쇼핑"),
    ("godomall", "한촌몰·고도몰(네이버페이 포함)"),
    ("coupang", "쿠팡 WING"),
    ("lotteon", "롯데ON"),
    ("ssg", "SSG.COM"),
    ("elevenst", "11번가"),
)


def render_field_dictionary(path: Path) -> str:
    entries = json.loads(path.read_text(encoding="utf-8"))
    lines = ["# 채널별 주문·배송 API 필드 사전", ""]
    for channel, label in CHANNELS:
        lines.extend((f"## {label}", "", "| 응답 경로 | DB 컬럼 | SQL 형식 | 분류 | 근거 |", "|---|---|---|---|---|"))
        selected = sorted(
            (entry for entry in entries if entry["channel"] == channel),
            key=lambda entry: (entry["response_path"], entry.get("column", "")),
        )
        for entry in selected:
            column = f"`{entry['column']}`" if entry.get("column") else "-"
            lines.append(
                f"| `{entry['response_path']}` | {column} | `{entry['sql_type']}` | "
                f"{entry['classification']} | {entry['evidence']} |"
            )
        lines.append("")
    return "\n".join(lines)
