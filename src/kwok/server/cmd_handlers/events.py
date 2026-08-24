from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from kwok.net.requset_context import RequestContext
from kwok.protocol.errors import InvalidParamsError
from kwok.protocol.rpc_model import (
    SubscribeReq,
    SubscribeResp,
    UnsubscribeReq,
    UnsubscribeResp,
)
from kwok.server.event import get_client_push


class SubscribeHandler:

    def __init__(self) -> None:
        self._bus = get_client_push()

    async def __call__(
            self, params: Any, ctx: RequestContext | None = None
    ) -> SubscribeResp:
        if ctx is None:
            raise InvalidParamsError("订阅需要请求上下文（connection_id）")
        try:
            req = SubscribeReq.model_validate({} if params is None else params)
        except ValidationError as exc:
            raise InvalidParamsError(f"无效订阅参数: {exc}") from exc
        self._bus.subscribe(ctx.connection_id, req.patterns)
        return SubscribeResp(connection_id=ctx.connection_id, patterns=req.patterns)


class UnsubscribeHandler:

    def __init__(self) -> None:
        self._bus = get_client_push()

    async def __call__(
            self, params: Any, ctx: RequestContext | None = None
    ) -> UnsubscribeResp:
        if ctx is None:
            raise InvalidParamsError("退订需要请求上下文（connection_id）")
        try:
            req = UnsubscribeReq.model_validate({} if params is None else params)
        except ValidationError as exc:
            raise InvalidParamsError(f"无效退订参数: {exc}") from exc
        self._bus.unsubscribe(ctx.connection_id, req.patterns)
        return UnsubscribeResp(patterns=req.patterns)
