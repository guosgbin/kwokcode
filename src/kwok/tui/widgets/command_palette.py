from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from textual.containers import Container
from textual.widget import Widget
from textual.widgets import OptionList
from textual.widgets.option_list import Option

# 命令注册表：斜杠弹层的过滤与 app._handle_command 的分发共用同一份，
# 避免弹层显示的命令与实际能执行的命令漂移。
COMMANDS: dict[str, str] = {
    "/compact": "压缩上下文",
    "/clear": "清屏",
    "/exit": "退出程序",
    "/help": "显示帮助",
}

_NONE_HINT = "无匹配命令"
# 命令名列宽：用于把描述对齐成列（命令名全 ASCII，空格填充即可对齐）
_NAME_WIDTH = max(len(name) for name in COMMANDS)


class CommandPalette(Container):
    """斜杠命令候选弹层。

    必须挂在 Screen 层（由 App 直接产出），不能作为 InputPanel 的子元素：
    Textual 会把超出父容器边界的绝对定位子元素裁剪掉，弹层悬浮在输入框上方
    天然越界，故以 Screen 为父、在 show() 后按输入面板的屏幕位置计算 offset。
    只提供视觉反馈 + Tab/点击补全；Enter 行为保持不变（提交当前文本）。
    """

    DEFAULT_CSS = """
    CommandPalette {
        position: absolute;
        width: 100%;
        height: auto;
        max-height: 12;
        background: $surface;
        border: round $accent;
        padding: 0 1;
        visibility: hidden;
    }
    CommandPalette.show {
        visibility: visible;
    }
    CommandPalette OptionList {
        height: auto;
        border: none;
        background: transparent;
    }
    CommandPalette OptionList:focus {
        border: none;
    }
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.options_list = OptionList()
        self._matches: list[str] = []
        self._input: Widget | None = None

    def compose(self) -> Iterable[Widget]:
        yield self.options_list

    # ---- 显示 / 过滤 ----

    @property
    def is_visible(self) -> bool:
        return self.has_class("show")

    def show(self, prefix: str) -> None:
        self._rebuild(prefix)
        self.add_class("show")
        # 等一帧布局（选项高度落定）再锚定到输入框正上方
        self.call_after_refresh(self._position)

    def hide(self) -> None:
        self.remove_class("show")

    def _rebuild(self, prefix: str) -> None:
        # 命令名含前导 "/"，prefix 来自 "/" 之后的输入，故比较 name[1:]
        matches = [name for name in COMMANDS if name[1:].startswith(prefix)]
        self._matches = matches
        self.options_list.clear_options()
        if not matches:
            self.options_list.add_option(Option(_NONE_HINT, disabled=True))
        else:
            # 行内显示描述：命令名列宽对齐；id 仍取命令名，保证
            # Tab 补全（_matches）与鼠标点选（option_id）拿到纯命令。
            self.options_list.add_options(
                [
                    Option(f"{name:<{_NAME_WIDTH}}  {COMMANDS[name]}", id=name)
                    for name in matches
                ]
            )
            self.options_list.highlighted = 0

    def _position(self) -> None:
        """锚定到输入面板正上方：offset.y = 输入框顶部 − 弹层自身高度。"""
        if self._input is None:
            try:
                self._input = self.app.query_one("#input")
            except Exception:
                return
        if self._input is None:
            return
        # region 相对 Screen（见 Widget.region 文档）；Screen 自身不滚动，
        # 输入面板顶部即屏幕坐标，减去弹层高度即浮在其正上方
        self.offset = (0, self._input.region.y - self.size.height)

    # ---- 高亮导航 ----

    def move_highlight(self, delta: int) -> None:
        if not self._matches:
            return
        opts = self.options_list
        n = len(self._matches)
        if opts.highlighted is None:
            opts.highlighted = 0
        else:
            opts.highlighted = (opts.highlighted + delta) % n

    def highlighted_command(self) -> str | None:
        if self.options_list.highlighted is None or not self._matches:
            return None
        return self._matches[self.options_list.highlighted]


__all__ = ["COMMANDS", "CommandPalette"]
