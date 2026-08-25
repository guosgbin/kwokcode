from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from kwok.net.requset_context import RequestContext
from kwok.protocol.errors import InvalidParamsError
from kwok.protocol.rpc_model import SessionCompactReq, SessionCompactResp
from kwok.server.session import SessionManager


class SessionCompactHandler:

    def __init__(self, sessions: SessionManager) -> None:
        self._sessions = sessions

    async def __call__(
            self, params: Any, ctx: RequestContext | None = None
    ) -> SessionCompactResp:
        if ctx is None:
            raise InvalidParamsError("压缩会话需要请求上下文（connection_id）")
        try:
            req = SessionCompactReq.model_validate({} if params is None else params)
        except ValidationError as exc:
            raise InvalidParamsError(f"无效会话压缩参数: {exc}") from exc
        result = await self._sessions.compact(req.session_id, ctx.connection_id)
        return SessionCompactResp(
            summary_path=str(result.summary_path),
            token_count=result.token_count,
            saved_tokens=result.saved_tokens,
        )
