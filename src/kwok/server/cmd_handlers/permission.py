from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from kwok.net.requset_context import RequestContext
from kwok.protocol.enums import INTERACTIVE_DECISIONS
from kwok.protocol.errors import InvalidParamsError
from kwok.protocol.rpc_model import PermissionRespondReq, PermissionRespondResp
from kwok.server.permissions import PermissionManager


class PermissionRespondHandler:
    """permission.respond：回传审批决策，resolve 对应 pending Future。

    decision 白名单限定为交互决策（allow_once/session_allow/deny_once/session_deny）；
    auto_*/timeout 仅服务端内部产生，客户端回传即视为非法参数。
    """

    def __init__(self, manager: PermissionManager) -> None:
        self._manager = manager

    async def __call__(
            self, params: Any, ctx: RequestContext | None = None
    ) -> PermissionRespondResp:
        try:
            req = PermissionRespondReq.model_validate({} if params is None else params)
        except ValidationError as exc:
            raise InvalidParamsError(f"无效审批回传参数: {exc}") from exc
        if req.decision not in INTERACTIVE_DECISIONS:
            raise InvalidParamsError(f"非法审批决策：{req.decision}")
        self._manager.respond(req.tool_use_id, req.decision)
        return PermissionRespondResp(tool_use_id=req.tool_use_id, decision=req.decision)
