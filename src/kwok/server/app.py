from __future__ import annotations

import asyncio
import logging
import signal
import time

from kwok.config import get_config
from kwok.log import setup_logging
from kwok.net.server import SocketServer
from kwok.server.cmd_handlers import HandlerManager
from kwok.server.event.client_bus import ClientEventPush
from kwok.server.event.manager import EventBusManager
from kwok.server.llm import LlmProvider, build_provider
from kwok.server.session import SessionManager, SessionStore
from kwok.server.tools import read_file_tool

logger = logging.getLogger(__name__)


class KwokApp:

    def __init__(
            self, provider: LlmProvider | None = None, bus: ClientEventPush | None = None
    ) -> None:

        self._eventBus = EventBusManager()
        self._clientEventPush = bus if bus is not None else ClientEventPush()
        self._provider = provider
        self._start_time = time.monotonic()
        config = get_config()
        self._sessions = SessionManager(
            store=SessionStore(config.projects_dir),
            bus=self._eventBus,
            get_provider=lambda: self._provider,
            tools=[read_file_tool.schema],
        )
        self._handler_manager = HandlerManager(
            event_bus=self._eventBus,
            client_bus=self._clientEventPush,
            get_start_time=lambda: self._start_time,
            get_provider=lambda: self._provider,
            sessions=self._sessions,
        )

    async def start(self) -> None:

        config = get_config()
        setup_logging(level=config.logging.level, log_file=config.logging.file)
        self._provider = build_provider(config)
        self._sessions.scan_orphans()

        self._eventBus.subscribe(self._clientEventPush.publish)

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
            self._handler_manager,
            bus=self._clientEventPush,
            eventBus=self._eventBus,
            on_disconnect=self._sessions.terminate_owned,
        )
        try:
            await socketServer.serve_forever(stop_event=stop_event)
        except OSError as exc:
            raise SystemExit(f"端口 {config.host} 被占用或不可用：{exc}") from exc
        finally:
            self._sessions.close_all()
