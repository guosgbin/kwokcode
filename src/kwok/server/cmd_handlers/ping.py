from __future__ import annotations

import datetime
import time
from collections.abc import Callable
from typing import Any
from zoneinfo import ZoneInfo

import kwok
from kwok.net.requset_context import RequestContext
from kwok.protocol.rpc_model import PingJsonRpcReq, PingJsonRpcResp


class PingHandler:

    def __init__(self, get_start_time: Callable[[], float]) -> None:
        self._get_start_time = get_start_time

    async def __call__(
            self, params: Any, ctx: RequestContext | None = None
    ) -> PingJsonRpcResp:
        PingJsonRpcReq.model_validate({} if params is None else params)
        received_at = datetime.datetime.now(ZoneInfo("Asia/Shanghai")).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        return PingJsonRpcResp(
            server_version=kwok.__version__,
            uptime_ms=int((time.monotonic() - self._get_start_time()) * 1000),
            received_at=received_at,
        )
