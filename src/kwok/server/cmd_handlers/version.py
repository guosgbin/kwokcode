from __future__ import annotations

from typing import Any

import kwok
from kwok.net.requset_context import RequestContext
from kwok.protocol.rpc_model import VersionJsonRpcReq, VersionJsonRpcResp


class VersionHandler:

    async def __call__(
            self, params: Any, ctx: RequestContext | None = None
    ) -> VersionJsonRpcResp:
        VersionJsonRpcReq.model_validate({} if params is None else params)
        return VersionJsonRpcResp(version=kwok.__version__)
