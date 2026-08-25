from __future__ import annotations

from rich.markup import escape
from rich.text import Text
from textual.binding import Binding
from textual.widget import Widget

from kwok.protocol.enums import PermissionDecision
from kwok.tui.messages import PermissionSelected

# 选项顺序即数字键 1/2/3/4 与 ←→ 游标顺序
_OPTIONS: list[tuple[PermissionDecision, str]] = [
    (PermissionDecision.ALLOW_ONCE, "允许一次"),
    (PermissionDecision.SESSION_ALLOW, "会话内允许"),
    (PermissionDecision.DENY_ONCE, "拒绝一次"),
    (PermissionDecision.SESSION_DENY, "会话内拒绝"),
]


class PermissionSelect(Widget):
    """内联审批控件（非 Modal）：展示工具名 + 参数预览 + 数字键决策。

    聚焦后按 1/2/3/4 任一键即发出 PermissionSelected 消息；
    由 App 侧发送 permission.respond 并卸载本控件（决策字符串全链路透传）。
    """

    # Textual 8.x Widget.can_focus 默认 False——不设 True 则 focus() 是空操作，
    # 数字键永远到不了 BINDINGS（按了没反应、焦点悬空）
    can_focus = True

    DEFAULT_CSS = """
    PermissionSelect {
        height: auto;
        padding: 0 2;
        background: $boost;
        border: round $accent;
        color: $text;
    }
    """

    BINDINGS = [
        Binding("1", "allow_once", "允许一次"),
        Binding("2", "session_allow", "会话内允许"),
        Binding("3", "deny_once", "拒绝一次"),
        Binding("4", "session_deny", "会话内拒绝"),
        Binding("left", "cursor_left", "← 上一个"),
        Binding("right", "cursor_right", "→ 下一个"),
        Binding("enter", "submit_selected", "确认选择"),
    ]

    def __init__(
            self,
            *,
            tool_use_id: str,
            tool_name: str,
            param_preview: str,
            timeout_s: float | None,
    ) -> None:
        super().__init__()
        self.tool_use_id = tool_use_id
        self._tool_name = tool_name
        self._param_preview = param_preview
        self._timeout_s = timeout_s
        self._submitted = False
        # ←→ 游标位置，默认第 1 项（允许一次）
        self._selected = 0

    def render(self) -> Text:
        timeout = (
            "无超时"
            if self._timeout_s is None or self._timeout_s <= 0
            else f"超时 {self._timeout_s:g}s"
        )
        options = "  ".join(self._option(i) for i in range(len(_OPTIONS)))
        return Text.from_markup(
            f"[b]授权请求[/b] [b]{escape(self._tool_name)}[/b] "
            f"[dim]{escape(self._param_preview)}[/dim]\n"
            f"{options}  [dim]（{timeout}）[/dim]"
        )

    def _option(self, index: int) -> str:
        """单个选项文本；当前游标项反显高亮。"""
        key = str(index + 1)
        label = _OPTIONS[index][1]
        if index == self._selected:
            return f"[reverse] {key} {label} [/reverse]"
        return f"[b]{key}[/b] {label}"

    def action_allow_once(self) -> None:
        self._submit(PermissionDecision.ALLOW_ONCE)

    def action_session_allow(self) -> None:
        self._submit(PermissionDecision.SESSION_ALLOW)

    def action_deny_once(self) -> None:
        self._submit(PermissionDecision.DENY_ONCE)

    def action_session_deny(self) -> None:
        self._submit(PermissionDecision.SESSION_DENY)

    def action_cursor_left(self) -> None:
        self._selected = (self._selected - 1) % len(_OPTIONS)
        self.refresh()

    def action_cursor_right(self) -> None:
        self._selected = (self._selected + 1) % len(_OPTIONS)
        self.refresh()

    def action_submit_selected(self) -> None:
        self._submit(_OPTIONS[self._selected][0])

    def _submit(self, decision: PermissionDecision) -> None:
        if self._submitted:
            return
        self._submitted = True
        self.post_message(PermissionSelected(tool_use_id=self.tool_use_id, decision=decision))
