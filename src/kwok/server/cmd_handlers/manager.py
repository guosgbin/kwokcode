from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from kwok.net.requset_context import RequestContext
from kwok.protocol.enums import Method
from kwok.protocol.errors import UnknownMethodError
from kwok.server.event.client_bus import ClientEventPush
from kwok.server.event.manager import EventBusManager
from kwok.server.llm import LlmProvider
from kwok.server.cmd_handlers.chat import ChatHandler
from kwok.server.cmd_handlers.events import (
    SubscribeHandler,
    TypesHandler,
    UnsubscribeHandler,
)
from kwok.server.cmd_handlers.ping import PingHandler
from kwok.server.cmd_handlers.version import VersionHandler

Handler = Callable[[Any, RequestContext | None], Awaitable[Any]]


class HandlerManager:

    def __init__(
            self,
            event_bus: EventBusManager,
            client_bus: ClientEventPush,
            get_start_time: Callable[[], float],
            get_provider: Callable[[], LlmProvider | None],
    ) -> None:
        self._handlers: dict[str, Handler] = {
            Method.PING: PingHandler(get_start_time),
            Method.VERSION: VersionHandler(),
            Method.CHAT: ChatHandler(event_bus, get_provider),
            Method.EVENT_SUBSCRIBE: SubscribeHandler(client_bus),
            Method.EVENT_UNSUBSCRIBE: UnsubscribeHandler(client_bus),
            Method.EVENT_TYPES: TypesHandler(client_bus),
        }

    async def dispatch(
            self, method: str, params: Any, ctx: RequestContext | None = None
    ) -> Any:
        handler = self._handlers.get(method)
        if handler is None:
            raise UnknownMethodError(method)
        return await handler(params, ctx)
