from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from kwok.net.requset_context import RequestContext
from kwok.protocol.errors import UnknownMethodError
from kwok.protocol.rpc_model import Method
from kwok.server.cmd_handlers.compact import SessionCompactHandler
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
    """Registry and dispatcher for all RPC method handlers.

    Maintains a mapping from RPC method names to their corresponding handler instances.
    The dispatch() method looks up the target handler and invokes it with request parameters
    and client context. Raises UnknownMethodError when no registered handler matches the method.

    Args:
        get_start_time: Callable returning the monotonic server start timestamp.
        get_provider: Callable to retrieve the active LLM provider instance.
        sessions: Manager for session lifecycle operations.
        permissions: Manager for client permission verification and responses.
    """
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
            Method.SESSION_COMPACT: SessionCompactHandler(sessions),
            Method.PERMISSION_RESPOND: PermissionRespondHandler(permissions),
        }

    async def dispatch(
            self, method: str, params: Any, ctx: RequestContext | None = None
    ) -> Any:
        """Route an incoming RPC request to the registered handler.

        Looks up the handler by RPC method name and executes it with given parameters
        and request context.

        Args:
            method: Name of the target RPC method.
            params: Raw RPC request parameters.
            ctx: Client connection request context, may be None.

        Returns:
            Handler execution result as the RPC response payload.

        Raises:
            UnknownMethodError: If no handler is registered for the requested method.
        """
        handler = self._handlers.get(method)
        if handler is None:
            raise UnknownMethodError(method)
        return await handler(params, ctx)
