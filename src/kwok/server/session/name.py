from __future__ import annotations

import re

_WHITESPACE_RE = re.compile(r"\s+")


def derive_name(prompt: str, limit: int) -> str:
    """从 prompt 派生会话名：strip → 折叠连续空白 → 截取前 limit 字符。"""
    return _WHITESPACE_RE.sub(" ", prompt.strip())[:limit]
