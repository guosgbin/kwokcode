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
    """RPC handler for client event subscription.

    Subscribes the current connection to specified event patterns.
    A valid request context containing connection_id is mandatory.
    Registered patterns will receive server‑pushed events once matched.
    """
    def __init__(self) -> None:
        self._bus = get_client_push()

    async def __call__(
            self, params: Any, ctx: RequestContext | None = None
    ) -> SubscribeResp:
        if ctx is None:
            raise InvalidParamsError("Subscription requires request context (connection_id)")
        try:
            req = SubscribeReq.model_validate({} if params is None else params)
        except ValidationError as exc:
            raise InvalidParamsError(f"Invalid subscription parameters: {exc}") from exc
        self._bus.subscribe(ctx.connection_id, req.patterns)
        return SubscribeResp(connection_id=ctx.connection_id, patterns=req.patterns)


class UnsubscribeHandler:
    """RPC handler for client event unsubscription.

    Removes event pattern subscriptions bound to the current connection.
    A valid request context containing connection_id is mandatory.
    The client will no longer receive events for the cancelled patterns.
    """

    def __init__(self) -> None:
        self._bus = get_client_push()

    async def __call__(
            self, params: Any, ctx: RequestContext | None = None
    ) -> UnsubscribeResp:
        if ctx is None:
            raise InvalidParamsError("Unsubscribe requires request context (connection_id)")
        try:
            req = UnsubscribeReq.model_validate({} if params is None else params)
        except ValidationError as exc:
            raise InvalidParamsError(f"Invalid unsubscribe parameters: {exc}") from exc
        self._bus.unsubscribe(ctx.connection_id, req.patterns)
        return UnsubscribeResp(patterns=req.patterns)
