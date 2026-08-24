from __future__ import annotations

import os
from pathlib import Path

from rich import box
from rich.console import Group
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

import kwok
from kwok.tui.state import UiState

# 角色色：与默认主题 builtin_dark 协调
_COL_ACCENT = "#FEA62B"

# 原 8×111 大图是 KWOKCODE 横排成一排（所以需要宽终端）。按用户思路，
# 从字母分界处切成 KWOK / CODE 两半、上下叠放，宽度 111 → 59，任意终端都放得下。
_LOGO_KWOK = """ 
 █████   ████ ██   ███   ██     ██████    █████   ████
░░███   ███░ ░██  ░███  ░██   ███░░░░███ ░░███   ███░ 
 ░███  ███   ░██  ░███  ░██  ███    ░░███ ░███  ███   
 ░███████    ░██  ░███  ░██ ░███     ░███ ░███████    
 ░███░░███   ░██  █████ ░██ ░███     ░███ ░███░░███   
 ░███ ░░███   ░░████░████░  ░░███    ███  ░███ ░░███  
 █████ ░░████   ░██ ░░██     ░░░██████░   █████ ░░████
░░░░░   ░░░░     ░░   ░░        ░░░░░░░    ░░░░░   ░░░░        
"""

_LOGO_CODE = """   
   █████████     ███████    ███████████   ████████████
  ███░░░░░███  ███░░░░░███ ░░███░░░░░███ ░░███░░░░░░░█
 ███     ░░░  ███     ░░███ ░███    ░░███ ░███    █  ░ 
░███         ░███      ░███ ░███     ░███ ░████████   
░███         ░███      ░███ ░███     ░███ ░███░░░░█   
░░███     ███░░███     ███  ░███     ███  ░███  ░    █
 ░░█████████  ░░░███████░   ███████████   ████████████
  ░░░░░░░░░     ░░░░░░░░░   ░░░░░░░░░░░░  ░░░░░░░░░░░░ 
"""

_TIPS = [
    "Enter 发送，Ctrl+J 换行",
    "↑/↓ 浏览历史命令",
    "/help 帮助 · /clear 清屏 · /exit 退出",
]

_DEFAULT_NEWS = ["首次启动，暂无更新记录"]


def recent_changelog(limit: int = 8) -> list[str]:
    """读 CHANGELOG.md 最新版本条目的变更要点；文件缺失时回退默认文案。"""
    path = Path("CHANGELOG.md")
    if not path.exists():
        return list(_DEFAULT_NEWS)
    bullets: list[str] = []
    in_latest = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            if in_latest:
                break
            if "[Unreleased]" not in line:
                in_latest = True
            continue
        if in_latest and line.startswith("- "):
            bullets.append(line[2:].strip())
            if len(bullets) >= limit:
                break
    return bullets or list(_DEFAULT_NEWS)


def _info_block(state: UiState) -> list[str]:
    model = state.model or "未配置模型"
    return [
        f"{model}",
        os.getcwd(),
    ]


def _logo_block(art: str, style: str) -> Text:
    """logo 文本块：去掉首尾空行与行尾空白，靠左对齐（不做居中）。

    各行内部相对位置由原图自带的前导空格决定；no_wrap 防止窄列里被折行。
    """
    lines = [line.rstrip() for line in art.splitlines() if line.strip()]
    return Text("\n".join(lines), style=style, no_wrap=True)


def _tips_block(changelog: list[str]) -> list[str | Text]:
    return [
        Text("Tips for getting started", style="bold"),
        *(f"· {tip}" for tip in _TIPS),
        "",
        Text("What's new", style="bold"),
        *(f"· {line}" for line in changelog),
    ]


def build_welcome(state: UiState, changelog: list[str] | None = None) -> Group:
    """构建欢迎横幅：参照 Claude Code 排版——左侧 KWOK/CODE 大 logo 靠左对齐，
    右侧两行（会话信息 | 使用提示）。
    """
    if changelog is None:
        changelog = recent_changelog()
    header = Rule(
        f" [bold {_COL_ACCENT}]KwokCode v{kwok.__version__}[/bold {_COL_ACCENT}] ",
        style="dim",
    )
    logo = Group(
        _logo_block(_LOGO_KWOK, f"bold {_COL_ACCENT}"),
        _logo_block(_LOGO_CODE, f"bold {_COL_ACCENT}"),
    )
    info = _info_block(state)
    tips = _tips_block(changelog)
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(justify="left", ratio=3, min_width=36)  # 左：logo
    table.add_column(min_width=5)  # 空间隔列：拉大 logo 与内容列之间的间距
    table.add_column(justify="left", ratio=2, min_width=32)  # 右：信息 + Tips
    table.add_row(logo, "", Group(*info, "", *tips))
    panel = Panel(table, box=box.ROUNDED, border_style="dim", padding=(0, 1))
    return Group(header, panel)


__all__ = ["build_welcome", "recent_changelog"]
