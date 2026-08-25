from __future__ import annotations

import difflib
from rich.markup import escape

_CONTEXT_LINES = 3
_MAX_LINES = 60


def render_diff(before: str, after: str) -> str:
    """行级 diff（双列行号 + 截断 + 颜色），供 TUI 展示 edit 改动。

    颜色：删除行红底、新增行绿底、context 行无背景。
    行内容用 rich.markup.escape 转义，保留 markup 标签。
    """
    b = before.splitlines()
    a = after.splitlines()
    diff = difflib.unified_diff(
        b, a, fromfile="before", tofile="after", lineterm="", n=_CONTEXT_LINES
    )

    out: list[str] = []
    from_n = to_n = 0
    for line in diff:
        if line.startswith("@@"):
            header = line.strip()
            try:
                parts = header.split(" ")
                from_n = _parse_hunk(parts[1])
                to_n = _parse_hunk(parts[2])
            except (IndexError, ValueError):
                from_n = to_n = 0
            continue
        if line.startswith("---") or line.startswith("+++"):
            continue
        if len(out) >= _MAX_LINES:
            out.append("…（diff 展示已截断）")
            break
        content = escape(line[1:])  # 去掉首字符后转义
        if line.startswith("-"):
            out.append(f"[on #5C1A1B]{from_n:>4} | {'':>4} | {content}[/on #5C1A1B]")
            from_n += 1
        elif line.startswith("+"):
            out.append(f"[on #1A3A1A]{'':>4} | {to_n:>4} | {content}[/on #1A3A1A]")
            to_n += 1
        else:
            out.append(f"{from_n:>4} | {to_n:>4} | {content}")
            from_n += 1
            to_n += 1
    return "\n".join(out)


def _parse_hunk(part: str) -> int:
    """hunk 片段如 '-1,3' / '+1' → 起始行号（1-based，无则 1）。"""
    return max(int(part.lstrip("-+").split(",")[0]), 1)