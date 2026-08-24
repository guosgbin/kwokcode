from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from textual import events
from textual.containers import Container, Horizontal
from textual.widget import Widget
from textual.widgets import Rule, Static, TextArea

from kwok.tui.messages import SubmitPrompt


class PromptTextArea(TextArea):
    """拦截 Enter（提交）/ Ctrl+J（换行），并支持 ↑/↓ 浏览历史命令。

    TextArea 默认在内部 keymap 处理 Enter 为换行、↑/↓ 为移动游标，父级绑定无法抢先，
    故子类化在 _on_key 层拦截。
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._history: list[str] = []
        self._history_index: int | None = None
        self._draft: str = ""

    async def _on_key(self, event: events.Key) -> None:
        if event.key == "enter":
            event.stop()
            event.prevent_default()
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
    """底部输入区：组合 PromptTextArea，暴露 启用/禁用/清空 操作。"""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.prompt_area = PromptTextArea(
            placeholder="输入消息，Enter 发送，Ctrl+J 换行"
        )

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
