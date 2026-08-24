from __future__ import annotations

import asyncio
import os
from collections.abc import Iterable

from textual.app import App
from textual.widget import Widget

from kwok.config import get_config
from kwok.protocol.errors import RpcConnectionError, RpcError
from kwok.tui.client import TuiClient
from kwok.tui.messages import ConnectionLost, ConnectResult, EventMessage, SubmitPrompt
from kwok.tui.renderer import EventRenderer
from kwok.tui.state import UiState
from kwok.tui.widgets import InputPanel, PromptTextArea, StatusBar, Transcript

_SUB_PATTERNS = ["turn.*", "step.*", "llm.*", "tool.**", "server.*"]


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
    ]

    def __init__(self) -> None:
        super().__init__()
        config = get_config()
        self.state = UiState(model=config.llm.model or "")
        self._client = TuiClient()
        self._renderer: EventRenderer | None = None
        self._shutting_down = False

    def compose(self) -> Iterable[Widget]:
        yield Transcript(id="transcript")
        yield InputPanel(id="input")
        yield StatusBar(id="status")

    # ---- 装配 ----

    def on_mount(self) -> None:
        self.title = "kwok-tui"
        self._renderer = EventRenderer(self.query_one(Transcript), self.state)
        self.query_one(PromptTextArea).focus()
        self.run_worker(self._run_client(), name="tui-client", exclusive=True)

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
        assert self._renderer is not None
        await self._renderer.handle(message.event)
        self._sync_status()
        self._sync_input()

    def on_submit_prompt(self, message: SubmitPrompt) -> None:
        if self.state.connection_status != "connected":
            return
        if self.state.turn_in_flight:
            return
        prompt = message.prompt.strip()
        if not prompt:
            return
        if prompt.startswith("/"):
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

    # ---- 命令与退出 ----

    def _handle_command(self, prompt: str) -> None:
        cmd = prompt.strip().lower()
        if cmd == "/exit":
            self.action_quit_app()
        elif cmd == "/help":
            self.query_one(Transcript).append_info(
                "可用命令：/exit 退出  /help 帮助  /clear 清屏"
            )
        elif cmd == "/clear":
            self.query_one(Transcript).clear()
        else:
            self.query_one(Transcript).add_error(f"未知命令：{cmd}")

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

    def _sync_status(self) -> None:
        self.query_one(StatusBar).render_state(self.state)

    def _sync_input(self) -> None:
        can_input = self.state.connection_status == "connected" and not self.state.turn_in_flight
        self.query_one(InputPanel).set_disabled(not can_input)


__all__ = ["KwokTuiApp"]
