from __future__ import annotations

from typing import Any

from rich.markup import escape
from rich.rule import Rule
from textual.containers import VerticalScroll
from textual.timer import Timer
from textual.widgets import Markdown, Static
from textual.widgets.markdown import MarkdownStream

from kwok.tui.diff_render import render_diff
from kwok.tui.state import UiState
from kwok.tui.widgets.welcome import build_welcome

# assistant 显示名（与用户消息的「You」对应）
ASSISTANT_NAME = "Kwok"

# 与默认主题 (builtin_dark) 协调的角色色：accent=琥珀 / primary=蓝 / success=绿 / error=红
_COL_ACCENT = "#FEA62B"
_COL_PRIMARY = "#0178D4"
_COL_SUCCESS = "#4EBF71"
_COL_ERROR = "#B93C5B"


def _preview(text: str, max_lines: int = 4, max_chars: int = 240) -> str:
    """工具结果预览（对标 Claude Code）：保留换行，行首加 ⎿，按行数/字符截断。"""
    lines = text.splitlines() or [""]
    out: list[str] = []
    used = 0
    truncated = False
    for line in lines[:max_lines]:
        remaining = max_chars - used
        if remaining <= 1:
            truncated = True
            break
        if len(line) > remaining:
            out.append(f"⎿ {line[: remaining - 1]}…")
            truncated = True
            break
        out.append(f"⎿ {line}")
        used += len(line) + 1
    if truncated or len(lines) > max_lines:
        out.append("⎿ …")
    return "\n".join(out)


class Transcript(VerticalScroll):
    """对话记录区：消息块列表 + 流式 markdown 渲染。

    用户消息/工具块/错误块为 Static；assistant 回复用 Markdown + MarkdownStream
    逐 token 追加渲染（代码块跨 chunk 自愈）。
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._stream: MarkdownStream | None = None
        self._tool_blocks: dict[str, tuple[Static, str, str]] = {}
        self._compact: Static | None = None
        self._compact_prefix: str = ""
        self._compact_dots: int = 0
        self._compact_timer: Timer | None = None

    # ---- 组装：内部关闭进行中的流式块 ----

    async def _close_stream(self) -> None:
        if self._stream is not None:
            await self._stream.stop()
            self._stream = None

    # ---- 启动欢迎横幅 ----

    def add_welcome(self, state: UiState) -> None:
        """在会话最顶部挂欢迎横幅（版本、大 logo、会话信息、Tips、What's new）。"""
        self.mount(Static(build_welcome(state), classes="msg welcome"))
        self.scroll_end(animate=False)

    # ---- 轮次分界线 ----

    def add_divider(self, label: str = "") -> None:
        """挂一条分隔线把相邻轮次隔开（label 居中显示在线上）。"""
        self.mount(Static(Rule(f"[dim] {label} [/dim]", style="dim")))
        self.scroll_end(animate=False)

    # ---- 用户 / 系统 / 错误消息 ----

    def append_user(self, text: str) -> None:
        self.mount(
            Static(
                f"[bold {_COL_PRIMARY}]You[/bold {_COL_PRIMARY}]\n{escape(text)}",
                classes="msg",
            )
        )
        self.scroll_end(animate=False)

    def append_info(self, text: str) -> None:
        self.mount(Static(f"[dim]{escape(text)}[/dim]"))
        self.scroll_end(animate=False)

    def begin_compact(self, trigger: str) -> None:
        """追加一条动态压缩行：每秒 +1 堆积点（1→6 循环），完成时由 end_compact 终结。"""
        if self._compact is not None:
            return
        self._compact_prefix = "检测到上下文占用偏高，正在" if trigger == "auto" else "正在"
        self._compact_dots = 0
        self._compact = Static(f"[dim]♻️ {self._compact_prefix}压缩上下文[/dim]")
        self.mount(self._compact)
        self.scroll_end(animate=False)
        self._compact_timer = self.set_interval(1.0, self._tick_compact)

    def _tick_compact(self) -> None:
        if self._compact is None:
            return
        self._compact_dots = self._compact_dots % 6 + 1
        dots = "●" * self._compact_dots
        self._compact.update(f"[dim]♻️ {self._compact_prefix}压缩上下文{dots}[/dim]")

    def end_compact(self, done_msg: str) -> None:
        """压缩结束：停掉 tick，把压缩行原位替换为结果文案。"""
        if self._compact_timer is not None:
            self._compact_timer.stop()
            self._compact_timer = None
        if self._compact is not None:
            self._compact.update(done_msg)
            self._compact = None
            self.scroll_end(animate=False)

    def add_error(self, message: str) -> None:
        self.mount(
            Static(
                f"[bold {_COL_ERROR}]✗[/bold {_COL_ERROR}] {escape(message)}", classes="msg"
            )
        )
        self.scroll_end(animate=False)

    # ---- assistant 流式 markdown ----

    async def start_assistant(self) -> None:
        await self._close_stream()
        self.mount(
            Static(f"[bold {_COL_ACCENT}]{ASSISTANT_NAME}[/bold {_COL_ACCENT}]", classes="msg")
        )
        md = Markdown("")
        self.mount(md)
        self._stream = Markdown.get_stream(md)

    async def append_delta(self, delta: str) -> None:
        if self._stream is None:
            await self.start_assistant()
        assert self._stream is not None
        await self._stream.write(delta)
        self.scroll_end(animate=False)

    async def finish_assistant(self) -> None:
        await self._close_stream()

    # ---- 工具块 ----

    def add_tool(self, tool_call_id: str, name: str, arguments: str) -> None:
        block = Static(
            f"[bold {_COL_ACCENT}]●[/bold {_COL_ACCENT}] "
            f"[bold]{escape(name)}[/bold]({escape(arguments)}) [dim]进行中…[/dim]",
            classes="msg tool-msg",
        )
        self._tool_blocks[tool_call_id] = (block, name, arguments)
        self.mount(block)
        self.scroll_end(animate=False)

    def update_tool(self, tool_call_id: str, result: str) -> None:
        entry = self._tool_blocks.get(tool_call_id)
        if entry is None:
            return
        block, name, arguments = entry
        display: str
        if name == "edit":
            display = self._render_edit_diff(result)
        else:
            display = f"[dim]{escape(_preview(result))}[/dim]"
        block.update(
            f"[{_COL_SUCCESS}]✓[/{_COL_SUCCESS}] [bold]{escape(name)}[/bold]"
            f"({escape(arguments)})\n{display}"
        )
        self.scroll_end(animate=False)

    def _render_edit_diff(self, result: str) -> str:
        """edit 结果：解析 before/after 渲染行级 diff；解析失败回退通用预览。"""
        import json

        try:
            data = json.loads(result.strip())
            diff = render_diff(data["before"], data["after"])
        except (json.JSONDecodeError, KeyError, TypeError, AttributeError):
            return f"[dim]{escape(_preview(result))}[/dim]"
        if not diff:
            return "[dim]无改动[/dim]"
        return f"[dim]{diff}[/dim]"

    # ---- 其他 ----

    def clear(self) -> None:
        if self._compact_timer is not None:
            self._compact_timer.stop()
            self._compact_timer = None
        self._compact = None
        self.remove_children()
        self._tool_blocks.clear()
        self._stream = None
