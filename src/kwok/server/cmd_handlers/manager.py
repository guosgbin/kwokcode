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
from kwok.server.cmd_handlers.permission import PermissionRespondHandler
from kwok.server.cmd_handlers.ping import PingHandler
from kwok.server.cmd_handlers.prompt import PromptHandler, SessionPromptHandler
from kwok.server.cmd_handlers.session import (
    SessionCloseHandler,
    SessionCreateHandler,
)
from kwok.server.cmd_handlers.version import VersionHandler
from kwok.server.llm import LlmProvider
from kwok.server.permissions import PermissionManager
from kwok.server.session import SessionManager

Handler = Callable[[Any, RequestContext | None], Awaitable[Any]]


class EventHandlerManager:

    def __init__(
            self,
            get_start_time: Callable[[], float],
            get_provider: Callable[[], LlmProvider | None],
            sessions: SessionManager,
            permissions: PermissionManager,
    ) -> None:
        self._handlers: dict[str, Handler] = {
            Method.PING: PingHandler(get_start_time),
            Method.VERSION: VersionHandler(),
            Method.PROMPT: PromptHandler(get_provider, sessions),
            Method.SESSION_PROMPT: SessionPromptHandler(get_provider, sessions),
            Method.EVENT_SUBSCRIBE: SubscribeHandler(),
            Method.EVENT_UNSUBSCRIBE: UnsubscribeHandler(),
            Method.SESSION_CREATE: SessionCreateHandler(sessions),
            Method.SESSION_CLOSE: SessionCloseHandler(sessions),
            Method.PERMISSION_RESPOND: PermissionRespondHandler(permissions),
        }

    async def dispatch(
            self, method: str, params: Any, ctx: RequestContext | None = None
    ) -> Any:
        handler = self._handlers.get(method)
        if handler is None:
            raise UnknownMethodError(method)
        return await handler(params, ctx)
