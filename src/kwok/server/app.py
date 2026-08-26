from __future__ import annotations

import asyncio
import logging
import signal
import time

from kwok.config import init_config
from kwok.log import init_logging
from kwok.net.server import SocketServer
from kwok.server.cmd_handlers import EventHandlerManager
from kwok.server.event import init_event_system
from kwok.server.llm import LlmProvider, build_provider
from kwok.server.mcp import McpServerManager, load_mcp_config
from kwok.server.permissions import PermissionManager, init_permissions
from kwok.server.session import SessionManager, SessionStore
from kwok.server.subagent import get_task_registry, init_subagent_system
from kwok.server.tools import get_tool_registry, init_tool_registry

logger = logging.getLogger(__name__)


class KwokApp:

    def __init__(self, provider: LlmProvider | None = None) -> None:
        self._provider = provider
        self._start_time = time.monotonic()
        self._permissions: PermissionManager | None = None
        self._mcp: McpServerManager | None = None

    async def start(self) -> None:
        config = init_config()
        init_logging(level=config.logging.level, log_file=config.logging.file)
        init_event_system()
        self._provider = build_provider(config)
        store = SessionStore(config.projects_dir)
        init_tool_registry(store)
        # MCP 挂载：启动时发现一次 + 注册进全局 registry（FR-018；不得每轮重注册，plan D7）
        config.mcp = load_mcp_config()
        self._mcp = McpServerManager()
        await self._mcp.start_all(config.mcp.servers)
        self._mcp.register_tools(get_tool_registry())
        self._permissions = init_permissions()
        assert self._provider is not None
        init_subagent_system(self._provider)
        self._sessions = SessionManager(
            store=store,
            get_provider=lambda: self._provider,
        )
        eventHandlerManager = EventHandlerManager(
            get_start_time=lambda: self._start_time,
            get_provider=lambda: self._provider,
            sessions=self._sessions,
            permissions=self._permissions,
        )
        self._sessions.scan_orphans()

        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()

        def _request_stop() -> None:
            logger.info("收到退出信号，开始优雅停机")
            stop_event.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _request_stop)
            except NotImplementedError:
                pass

        assert self._permissions is not None

        def _on_disconnect(connection_id: str) -> None:
            # 组合回调：先清该连接各 session 的 pending 审批，再级联取消后台子任务，最后终止会话本身
            assert self._permissions is not None
            session_ids = self._sessions.sessions_for_connection(connection_id)
            for session_id in session_ids:
                self._permissions.cancel_session(session_id)
            try:
                get_task_registry().cancel_by_session(session_ids)
            except RuntimeError:
                # subagent 系统未初始化（极早期断连）：清理路径不允许抛错
                pass
            self._sessions.terminate_owned(connection_id)

        socketServer = SocketServer(
            config.host,
            config.port,
            eventHandlerManager,
            on_disconnect=_on_disconnect,
        )
        try:
            await socketServer.serve_forever(stop_event=stop_event)
        except OSError as exc:
            raise SystemExit(f"端口 {config.host} 被占用或不可用：{exc}") from exc
        finally:
            if self._permissions is not None:
                self._permissions.shutdown()
            if self._mcp is not None:
                await self._mcp.stop_all()  # 关闭全部 MCP client（无残留子进程，FR-014）
            self._sessions.close_all()
