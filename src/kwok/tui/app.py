from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
from collections.abc import Iterable

from textual.app import App
from textual.widget import Widget
from textual.widgets import OptionList

from kwok.config import get_config
from kwok.protocol.errors import RpcConnectionError, RpcError
from kwok.protocol.events import (
    PermissionDeniedEvent,
    PermissionGrantedEvent,
    PermissionRequestedEvent,
)
from kwok.server.skill import SkillLoader
from kwok.tui.client import TuiClient
from kwok.tui.messages import (
    ConnectionLost,
    ConnectResult,
    EventMessage,
    PermissionSelected,
    SubmitPrompt,
)
from kwok.tui.renderer import EventRenderer
from kwok.tui.state import UiState
from kwok.tui.widgets import (
    InputPanel,
    PermissionSelect,
    PromptTextArea,
    StatusBar,
    Transcript,
)
from kwok.tui.widgets.command_palette import COMMANDS, CommandPalette

_SUB_PATTERNS = ["turn.*", "step.*", "llm.*", "tool.**", "server.*", "permission.*", "context.*"]

logger = logging.getLogger(__name__)


def _write_clipboard(text: str) -> bool:
    """跨平台写入系统剪贴板（macOS pbcopy / Linux wl-copy|xclip|xsel）。"""
    for cmd in ("pbcopy", "wl-copy", "xclip", "xsel"):
        exe = shutil.which(cmd)
        if exe is None:
            continue
        try:
            subprocess.run([exe], input=text.encode("utf-8"), check=False)
            return True
        except OSError:
            continue
    return False


class KwokTuiApp(App[None]):
    """KwokTui 主应用：连接 server、消费事件流渲染界面。

    事件消费跑在 run_worker（同一 asyncio loop），经 post_message 投递回 UI；
    客户端生命周期（connect/subscribe/session）与 UI 完全解耦（宪法 I/III/IV）。
    """

    CSS = """
    Screen {
        layout: vertical;
    }
    #transcript {
        height: 1fr;
        padding: 1 2 1 2;
        scrollbar-gutter: stable;
    }
    #transcript .msg {
        margin-top: 1;
        padding: 0 1;
    }
    #transcript .welcome {
        margin-top: 0;
        margin-bottom: 1;
    }
    #transcript .tool-msg {
        margin-left: 2;
        margin-right: 2;
    }
    #input {
        height: auto;
        max-height: 40%;
    }
    #input Rule {
        color: $accent;
        margin: 0;
    }
    #input .prompt-row {
        height: auto;
        padding: 0 2;
    }
    #input .prompt-mark {
        width: 1;
        margin-right: 1;
        color: $accent;
        content-align: left top;
    }
    #input:focus-within .prompt-mark {
        text-style: bold;
    }
    #input PromptTextArea {
        height: auto;
        max-height: 8;
        width: 1fr;
        border: none;
    }
    #input PromptTextArea:focus {
        border: none;
    }
    #status {
        height: auto;
        background: $panel;
        color: $text-muted;
        padding: 0 2;
    }
    """

    BINDINGS = [
        ("ctrl+q", "quit_app", "退出"),
        ("escape", "quit_app", "退出"),
        ("ctrl+y", "copy_selection", "复制选中区"),
    ]

    def __init__(self) -> None:
        super().__init__()
        config = get_config()
        self.state = UiState(model=config.llm.model or "")
        self._client = TuiClient()
        self._renderer: EventRenderer | None = None
        self._shutting_down = False
        # tool_use_id → 审批控件；granted/denied 或 respond 后卸载（幂等去重）
        self._permission_widgets: dict[str, PermissionSelect] = {}
        # 斜杠命令弹层：挂 Screen 层（作为 InputPanel 子元素会被裁剪）
        self._palette = CommandPalette()

    def compose(self) -> Iterable[Widget]:
        yield Transcript(id="transcript")
        yield InputPanel(id="input")
        yield StatusBar(id="status")
        # 弹层最后产出：绝对定位悬浮在输入面板上方，DOM 靠后保证盖住 Transcript
        yield self._palette

    # ---- 装配 ----

    def on_mount(self) -> None:
        self.title = "kwok-tui"
        self._renderer = EventRenderer(self.query_one(Transcript), self.state)
        self.query_one(InputPanel).bind_palette(self._palette)
        try:
            skills = SkillLoader().list_all_skills(os.getcwd())
            self._palette.reset_extra(
                {f"/{item['name']}": item["description"] for item in skills}
            )
        except Exception:
            pass
        self.query_one(PromptTextArea).focus()
        self.run_worker(self._run_client(), name="tui-client", exclusive=True)

    def on_option_list_option_selected(
        self, message: OptionList.OptionSelected
    ) -> None:
        """鼠标点选弹层候选：补全命令并回到输入框。"""
        if message.option_id is None:
            return
        panel = self.query_one(InputPanel)
        panel.prompt_area.complete_command(message.option_id)
        panel.prompt_area.focus()

    # ---- 客户端 worker：连接/订阅/建会话/事件迭代 ----

    async def _run_client(self) -> None:
        try:
            await self._client.connect()
        except RpcConnectionError as exc:
            self.post_message(ConnectResult(ok=False, error=str(exc)))
            return
        try:
            _, events = await self._client.subscribe(_SUB_PATTERNS)
            session_id = await self._client.create_session(os.getcwd())
            self.post_message(ConnectResult(ok=True, session_id=session_id))
            async for event in events:
                if self._shutting_down:
                    return
                self.post_message(EventMessage(event))
        except asyncio.CancelledError:
            raise
        except (RpcConnectionError, RpcError) as exc:
            if not self._shutting_down:
                self.post_message(ConnectionLost(str(exc)))
        except Exception as exc:
            if not self._shutting_down:
                self.post_message(ConnectionLost(f"客户端异常：{exc}"))

    # ---- 事件处理 ----

    def on_connect_result(self, message: ConnectResult) -> None:
        transcript = self.query_one(Transcript)
        if message.ok:
            self.state.session_id = message.session_id
            self.state.connection_status = "connected"
            transcript.add_welcome(self.state)
            transcript.append_info(f"已连接 kwok-server，会话 {message.session_id}")
        else:
            self.state.connection_status = "error"
            self.state.last_error = message.error
            transcript.add_error(f"无法连接 kwok-server：{message.error}")
            self.notify(f"无法连接 kwok-server：{message.error}", severity="error")
        self._sync_status()
        self._sync_input()

    def on_connection_lost(self, message: ConnectionLost) -> None:
        self.state.connection_status = "disconnected"
        self.state.last_error = message.error
        # message.error 已含上下文（如「连接中断: …」），避免重复前缀
        self.query_one(Transcript).add_error(message.error)
        self.notify(message.error, severity="error")
        self._sync_status()
        self._sync_input()

    async def on_event_message(self, message: EventMessage) -> None:
        event = message.event
        # Textual 8.x 会重抛消息处理器异常导致整个 TUI 闪退——这里兜底转成
        # 会话内错误提示，保证任何单个事件处理异常都不至于击穿进程。
        try:
            if isinstance(event, PermissionRequestedEvent):
                await self._mount_permission_select(event)
            elif isinstance(event, PermissionGrantedEvent):
                await self._finish_permission(
                    event.tool_use_id, f"工具 {event.tool_name} 已批准（{event.decision}）"
                )
            elif isinstance(event, PermissionDeniedEvent):
                await self._finish_permission(
                    event.tool_use_id, f"工具 {event.tool_name} 已拒绝（{event.decision}）"
                )
            else:
                assert self._renderer is not None
                await self._renderer.handle(event)
        except Exception as exc:
            logger.exception("事件处理异常 event=%s", type(event).__name__)
            self.query_one(Transcript).add_error(f"事件处理异常：{exc}")
        self._sync_status()
        self._sync_input()

    # ---- 权限审批 ----

    async def _mount_permission_select(self, event: PermissionRequestedEvent) -> None:
        """挂载内联审批控件（幂等去重），聚焦后由数字键决策。"""
        if event.tool_use_id in self._permission_widgets:
            return
        widget = PermissionSelect(
            tool_use_id=event.tool_use_id,
            tool_name=event.tool_name,
            param_preview=event.param_preview,
            timeout_s=event.timeout_s,
        )
        self._permission_widgets[event.tool_use_id] = widget
        await self.mount(widget, before=self.query_one(InputPanel))
        widget.focus()

    async def _remove_permission_widget(self, tool_use_id: str) -> None:
        widget = self._permission_widgets.pop(tool_use_id, None)
        if widget is not None:
            await widget.remove()

    async def _finish_permission(self, tool_use_id: str, note: str) -> None:
        await self._remove_permission_widget(tool_use_id)
        self.query_one(Transcript).append_info(note)

    async def on_permission_selected(self, message: PermissionSelected) -> None:
        """用户按键决策：卸载控件并回传 permission.respond。

        整个处理器兜底异常：卸载控件或回传 RPC 的任何异常都只落成会话内
        错误提示，不向外抛（Textual 8.x 会把处理器异常重抛导致 TUI 闪退）。
        """
        try:
            await self._remove_permission_widget(message.tool_use_id)
            await self._client.send_permission_respond(
                message.tool_use_id, message.decision
            )
        except (RpcError, RpcConnectionError) as exc:
            self.query_one(Transcript).add_error(f"审批回传失败：{exc}")
        except Exception as exc:
            logger.exception("审批按键处理异常 tool_use_id=%s", message.tool_use_id)
            self.query_one(Transcript).add_error(f"审批处理异常：{exc}")

    def on_submit_prompt(self, message: SubmitPrompt) -> None:
        if self.state.connection_status != "connected":
            return
        if self.state.turn_in_flight:
            return
        prompt = message.prompt.strip()
        if not prompt:
            return
        if prompt.startswith("/"):
            # 内建命令本地分发；非内建 `/xxx` 视为 skill 调用，落到下方普通 prompt 管道，
            # 由服务端解析 /skill 并替换 $ARGUMENTS。
            if prompt.strip().split(maxsplit=1)[0].lower() in COMMANDS:
                self.query_one(Transcript).append_user(prompt)
                self.query_one(InputPanel).clear()
                self._handle_command(prompt)
                return
        self.state.turn_count += 1
        self.query_one(Transcript).add_divider(f" 第 {self.state.turn_count} 轮 ")
        self.state.turn_in_flight = True
        self.query_one(Transcript).append_user(prompt)
        self.query_one(InputPanel).clear()
        self._sync_status()
        self._sync_input()
        self.run_worker(
            self._send_prompt(prompt), name=f"prompt-{self.state.session_id}", exclusive=False
        )

    async def _send_prompt(self, prompt: str) -> None:
        try:
            await self._client.prompt(prompt, self.state.session_id)
        except RpcError as exc:
            self.state.turn_in_flight = False
            self.query_one(Transcript).add_error(f"发送失败 [{exc.code}]：{exc.message}")
            self._sync_status()
            self._sync_input()

    async def _send_compact(self) -> None:
        """手动压缩：发 session.compact IPC；成功后 ⚡ 横幅由 ContextCompactedEvent 渲染。"""
        try:
            await self._client.compact(self.state.session_id)
        except (RpcError, RpcConnectionError) as exc:
            self.query_one(Transcript).add_error(f"压缩失败：{exc}")

    # ---- 命令与退出 ----

    def _handle_command(self, prompt: str) -> None:
        cmd = prompt.strip().lower()
        # 弹层与分发共用 COMMANDS 注册表：未注册的命令一律报未知
        if cmd not in COMMANDS:
            self.query_one(Transcript).add_error(f"未知命令：{cmd}")
            return
        if cmd == "/exit":
            self.action_quit_app()
        elif cmd == "/help":
            self.query_one(Transcript).append_info(
                "可用命令：" + "  ".join(f"{name} {desc}" for name, desc in COMMANDS.items())
            )
        elif cmd == "/clear":
            self.query_one(Transcript).clear()
        elif cmd == "/compact":
            if self.state.turn_in_flight:
                self.query_one(Transcript).append_info("turn 进行中，无法压缩")
            else:
                self.run_worker(
                    self._send_compact(), name=f"compact-{self.state.session_id}"
                )

    def action_quit_app(self) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True
        self.run_worker(self._shutdown(), name="shutdown", exclusive=True)

    async def _shutdown(self) -> None:
        if self.state.session_id:
            try:
                await self._client.close_session(self.state.session_id)
            except (RpcError, RpcConnectionError):
                pass
        await self._client.close()
        self.exit(return_code=0)

    # ---- 状态同步 ----

    def copy_text(self, text: str) -> None:
        """复制文本到剪贴板；失败时给出明确提示（缺少剪贴板命令）。"""
        if _write_clipboard(text):
            self.notify(f"已复制 {len(text)} 字符", title="剪贴板")
        else:
            self.query_one(Transcript).add_error(
                "复制失败：未找到 pbcopy/wl-copy/xclip/xsel 剪贴板命令"
            )

    def action_copy_selection(self) -> None:
        """Ctrl+Y 复制当前拖选的文本（Textual 原生选区，消息块默认允许选择）。"""
        selected = self.screen.get_selected_text()
        if not selected:
            self.notify("未选中文本，请先拖选要复制的内容")
            return
        self.copy_text(selected)

    def _sync_status(self) -> None:
        self.query_one(StatusBar).render_state(self.state)

    def _sync_input(self) -> None:
        can_input = self.state.connection_status == "connected" and not self.state.turn_in_flight
        self.query_one(InputPanel).set_disabled(not can_input)


__all__ = ["KwokTuiApp"]
