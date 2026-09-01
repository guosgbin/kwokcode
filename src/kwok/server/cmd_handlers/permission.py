from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from kwok.net.requset_context import RequestContext
from kwok.protocol.enums import INTERACTIVE_DECISIONS
from kwok.protocol.errors import InvalidParamsError
from kwok.protocol.rpc_model import PermissionRespondReq, PermissionRespondResp
from kwok.server.permissions import PermissionManager


class PermissionRespondHandler:
    """RPC handler for responding to pending permission approval requests.

    Receives client approval decisions and resolves the pending permission future.
    Only interactive decisions defined in INTERACTIVE_DECISIONS are accepted.
    Auto‑generated or timeout decisions are produced internally by the server and
    rejected if submitted from a client.

    Args:
        manager: Manager instance to handle pending permission responses.
    """

    def __init__(self, manager: PermissionManager) -> None:
        self._manager = manager

    async def __call__(
            self, params: Any, ctx: RequestContext | None = None
    ) -> PermissionRespondResp:
        try:
            req = PermissionRespondReq.model_validate({} if params is None else params)
        except ValidationError as exc:
            raise InvalidParamsError(f"Invalid permission response parameters:: {exc}") from exc
        if req.decision not in INTERACTIVE_DECISIONS:
            raise InvalidParamsError(f"Illegal permission decision: {req.decision}")
        self._manager.respond(req.tool_use_id, req.decision)
        return PermissionRespondResp(tool_use_id=req.tool_use_id, decision=req.decision)
