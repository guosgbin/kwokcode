from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from kwok.net.requset_context import RequestContext
from kwok.protocol.errors import UnknownMethodError
from kwok.protocol.rpc_model import Method
from kwok.server.cmd_handlers.events import (
    SubscribeHandler,
    UnsubscribeHandler,
)
from kwok.server.cmd_handlers.ping import PingHandler
from kwok.server.cmd_handlers.prompt import PromptHandler
from kwok.server.cmd_handlers.session import (
    SessionCloseHandler,
    SessionCreateHandler,
)
from kwok.server.cmd_handlers.version import VersionHandler
from kwok.server.event.client_bus import ClientEventPush
from kwok.server.event.manager import EventBusManager
from kwok.server.llm import LlmProvider
from kwok.server.session import SessionManager

Handler = Callable[[Any, RequestContext | None], Awaitable[Any]]


class HandlerManager:

    def __init__(
            self,
            event_bus: EventBusManager,
            client_bus: ClientEventPush,
            get_start_time: Callable[[], float],
            get_provider: Callable[[], LlmProvider | None],
            sessions: SessionManager,
    ) -> None:
        self._handlers: dict[str, Handler] = {
            Method.PING: PingHandler(get_start_time),
            Method.VERSION: VersionHandler(),
            Method.PROMPT: PromptHandler(event_bus, get_provider, sessions),
            Method.EVENT_SUBSCRIBE: SubscribeHandler(client_bus),
            Method.EVENT_UNSUBSCRIBE: UnsubscribeHandler(client_bus),
            Method.SESSION_CREATE: SessionCreateHandler(sessions),
            Method.SESSION_CLOSE: SessionCloseHandler(sessions),
        }

    async def dispatch(
            self, method: str, params: Any, ctx: RequestContext | None = None
    ) -> Any:
        handler = self._handlers.get(method)
        if handler is None:
            raise UnknownMethodError(method)
        return await handler(params, ctx)
