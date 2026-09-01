from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from kwok.net.requset_context import RequestContext
from kwok.protocol.errors import InvalidParamsError
from kwok.protocol.rpc_model import (
    SessionCloseReq,
    SessionCloseResp,
    SessionCreateReq,
    SessionCreateResp,
)
from kwok.server.session import SessionManager


class SessionCreateHandler:
    """Creates a new interactive session via RPC request.

    Args:
        sessions: Manager that maintains all session instances and lifecycle logic.
    """

    def __init__(self, sessions: SessionManager) -> None:
        self._sessions = sessions

    async def __call__(
            self, params: Any, ctx: RequestContext | None = None
    ) -> SessionCreateResp:
        if ctx is None:
            raise InvalidParamsError("Session creation requires request context (connection_id)")
        try:
            req = SessionCreateReq.model_validate({} if params is None else params)
        except ValidationError as exc:
            raise InvalidParamsError(f"Invalid session creation parameters: {exc}") from exc
        session = self._sessions.create(
            mode="interactive",
            title="",
            cwd=req.cwd,
            owner=ctx.connection_id,
            name=req.name,
        )
        return SessionCreateResp(session_id=session.id, name=session.meta.name)


class SessionCloseHandler:
    """Closes an existing session via RPC request.

    Args:
        sessions: Manager that maintains all session instances and lifecycle logic.
    """

    def __init__(self, sessions: SessionManager) -> None:
        self._sessions = sessions

    async def __call__(
            self, params: Any, ctx: RequestContext | None = None
    ) -> SessionCloseResp:
        if ctx is None:
            raise InvalidParamsError("Session closing requires request context (connection_id)")
        try:
            req = SessionCloseReq.model_validate({} if params is None else params)
        except ValidationError as exc:
            raise InvalidParamsError(f"Invalid session closing parameters: {exc}") from exc
        self._sessions.close(req.session_id, ctx.connection_id)
        return SessionCloseResp(session_id=req.session_id)
