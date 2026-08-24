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
from kwok.server.session import SessionManager, SessionStore
from kwok.server.tools import read_file_tool

logger = logging.getLogger(__name__)


class KwokApp:

    def __init__(self, provider: LlmProvider | None = None) -> None:
        self._provider = provider
        self._start_time = time.monotonic()

    async def start(self) -> None:
        config = init_config()
        init_logging(level=config.logging.level, log_file=config.logging.file)
        init_event_system()
        self._provider = build_provider(config)
        self._sessions = SessionManager(
            store=SessionStore(config.projects_dir),
            get_provider=lambda: self._provider,
            tools=[read_file_tool.schema],
        )
        eventHandlerManager = EventHandlerManager(
            get_start_time=lambda: self._start_time,
            get_provider=lambda: self._provider,
            sessions=self._sessions,
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

        socketServer = SocketServer(
            config.host,
            config.port,
            eventHandlerManager,
            on_disconnect=self._sessions.terminate_owned,
        )
        try:
            await socketServer.serve_forever(stop_event=stop_event)
        except OSError as exc:
            raise SystemExit(f"端口 {config.host} 被占用或不可用：{exc}") from exc
        finally:
            self._sessions.close_all()
