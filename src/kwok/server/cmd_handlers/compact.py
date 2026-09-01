from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from kwok.net.requset_context import RequestContext
from kwok.protocol.errors import InvalidParamsError
from kwok.protocol.rpc_model import SessionCompactReq, SessionCompactResp
from kwok.server.session import SessionManager


class SessionCompactHandler:
    """RPC handler for session compaction.

    Compresses the specified session to reduce token consumption.
    returning compacted summary path, total token count and saved token count.

    Args:
        sessions: Manager instance responsible for session lifecycle and compaction logic.
    """

    def __init__(self, sessions: SessionManager) -> None:
        self._sessions = sessions

    async def __call__(
            self, params: Any, ctx: RequestContext | None = None
    ) -> SessionCompactResp:
        if ctx is None:
            raise InvalidParamsError("Session compaction requires request context (connection_id)")
        try:
            req = SessionCompactReq.model_validate({} if params is None else params)
        except ValidationError as exc:
            raise InvalidParamsError(f"Invalid session compaction parameters: {exc}") from exc
        result = await self._sessions.compact(req.session_id, ctx.connection_id)
        return SessionCompactResp(
            summary_path=str(result.summary_path),
            token_count=result.token_count,
            saved_tokens=result.saved_tokens,
        )
