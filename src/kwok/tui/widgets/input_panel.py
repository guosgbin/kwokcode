from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from textual import events
from textual.containers import Container, Horizontal
from textual.widget import Widget
from textual.widgets import Rule, Static, TextArea

from kwok.tui.messages import SubmitPrompt
from kwok.tui.widgets.command_palette import CommandPalette


class PromptTextArea(TextArea):
    """拦截 Enter（提交）/ Ctrl+J（换行），支持 ↑/↓ 浏览历史，并驱动斜杠命令弹层。

    TextArea 默认在内部 keymap 处理 Enter 为换行、↑/↓ 为移动游标，父级绑定无法抢先，
    故子类化在 _on_key 层拦截。弹层可见时 ↑/↓/Tab/Esc 让位给命令补全；
    Enter 仅把高亮命令补全进输入框（与 Tab/点击一致），再按一次才发送——
    给用户在命令后补实参（如 `/review src/foo.py`）留出机会。
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._history: list[str] = []
        self._history_index: int | None = None
        self._draft: str = ""
        self._palette: CommandPalette | None = None

    def bind_palette(self, palette: CommandPalette) -> None:
        self._palette = palette

    async def _on_key(self, event: events.Key) -> None:
        palette = self._palette
        if palette is not None and palette.is_visible:
            # 弹层优先：↑/↓ 切候选，Tab/Shift+Tab 补全，Esc 关闭，
            # Enter 发送高亮命令。stop + prevent_default 阻止事件冒泡到
            # Screen 的 tab→focus_next 与 App 的 escape→quit_app。
            if event.key in ("up", "down"):
                event.stop()
                event.prevent_default()
                palette.move_highlight(-1 if event.key == "up" else 1)
                return
            if event.key in ("tab", "shift+tab"):
                event.stop()
                event.prevent_default()
                self._complete_from_palette()
                return
            if event.key == "escape":
                event.stop()
                event.prevent_default()
                palette.hide()
                return
        if event.key == "enter":
            event.stop()
            event.prevent_default()
            if palette is not None and palette.is_visible:
                command = palette.highlighted_command()
                if command is not None:
                    # 高亮候选上按 Enter：仅补全命令，不发送——等待用户补实参后再 Enter
                    self.complete_command(command)
                    return
            self._record_history()
            self.post_message(SubmitPrompt(self.text))
            return
        if event.key == "ctrl+j":
            # ctrl+j（\n）全终端通用；shift+enter 仅 kitty 协议可区分，故不使用
            event.stop()
            event.prevent_default()
            self.insert("\n")
            return
        if event.key == "up" and self._can_browse_back():
            event.stop()
            event.prevent_default()
            self._browse_history(-1)
            return
        if event.key == "down" and self._can_browse_forward():
            event.stop()
            event.prevent_default()
            self._browse_history(1)
            return
        await super()._on_key(event)

    # ---- 斜杠命令弹层 ----

    def _on_text_area_changed(self, message: TextArea.Changed) -> None:
        """文本变化驱动弹层：以 "/" 开头且首个词尚未是完整命令时显示并过滤，否则隐藏。

        首个词命中完整命令名即隐藏——覆盖 "/review" 与 "/review src" 两种情形：
        补全后弹层不随空格/实参复现，避免干扰后续输入；若弹层可见时按 Enter，
        也不会误把已补的实参覆盖回裸命令。
        """
        palette = self._palette
        if palette is None:
            return
        text = self.text
        if text.startswith("/"):
            body = text[1:]
            first = body.split()[0].lower() if body.split() else ""
            if first in {name[1:].lower() for name in palette.all_commands}:
                palette.hide()
                return
            palette.show(first)
        else:
            palette.hide()

    def _complete_from_palette(self) -> None:
        if self._palette is None:
            return
        command = self._palette.highlighted_command()
        if command is None:
            return
        self.complete_command(command)

    def complete_command(self, command: str) -> None:
        """把命令写回输入框（Tab / 鼠标点选共用）。"""
        palette = self._palette
        if palette is not None:
            palette.hide()
        self.text = command
        self.move_cursor(self.document.end)

    # ---- 历史命令浏览 ----

    def _record_history(self) -> None:
        text = self.text.strip()
        if text and (not self._history or self._history[-1] != text):
            self._history.append(text)
        self._history_index = None
        self._draft = ""

    def _can_browse_back(self) -> bool:
        if not self._history:
            return False
        # 已在历史浏览中，或游标位于首行（单行输入/多行首行）时回退
        if self._history_index is not None:
            return True
        return self.cursor_location[0] == 0

    def _can_browse_forward(self) -> bool:
        return self._history_index is not None

    def _browse_history(self, delta: int) -> None:
        n = len(self._history)
        if self._history_index is None:
            if delta < 0:
                self._draft = self.text
                self._history_index = n - 1
            else:
                return
        else:
            self._history_index += delta
            if self._history_index >= n:
                self._history_index = None
                self.text = self._draft
                self.move_cursor(self.document.end)
                return
            if self._history_index < 0:
                self._history_index = 0
        assert self._history_index is not None
        self.text = self._history[self._history_index]
        self.move_cursor(self.document.end)


class InputPanel(Container):
    """底部输入区：组合 PromptTextArea，暴露 启用/禁用/清空 操作。

    斜杠命令弹层（CommandPalette）由 App 挂在 Screen 层，经 bind_palette 注入；
    弹层是绝对定位、运行时锚定到输入框上方，不能作为本组件的子元素（会被裁剪）。
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.prompt_area = PromptTextArea(
            placeholder="输入消息，Enter 发送，Ctrl+J 换行，，Ctrl+Q 退出，，Ctrl+Y 复制"
        )

    def bind_palette(self, palette: CommandPalette) -> None:
        self.prompt_area.bind_palette(palette)

    def compose(self) -> Iterable[Widget]:
        # 上下两条贯穿横线 + 左侧 ">" 提示符（替代原来的方框）
        yield Rule()
        with Horizontal(classes="prompt-row"):
            yield Static(">", classes="prompt-mark")
            yield self.prompt_area
        yield Rule()

    def clear(self) -> None:
        self.prompt_area.clear()

    def set_disabled(self, disabled: bool) -> None:
        was_disabled = self.prompt_area.disabled
        self.prompt_area.disabled = disabled
        if was_disabled and not disabled:
            self.prompt_area.focus()
