from __future__ import annotations

import sys
import time
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from kwok.cli.cmd.resp_printer import print_formatter
from kwok.net.client import SocketClient
from kwok.protocol.errors import RpcConnectionError, RpcError
from kwok.protocol.rpc_model import (
    BaseRpcReq,
    Method,
    PingJsonRpcReq,
    PingJsonRpcResp,
    VersionJsonRpcReq,
    VersionJsonRpcResp,
)

_REQ_MAP: dict[Method, Callable[[], BaseRpcReq]] = {
    Method.PING: PingJsonRpcReq,
    Method.VERSION: VersionJsonRpcReq,
}

_RESP_MAP: dict[Method, type[Any]] = {
    Method.PING: PingJsonRpcResp,
    Method.VERSION: VersionJsonRpcResp,
}


async def run(method: Method, port: int) -> int:
    start_time = time.monotonic()
    req_cls = _REQ_MAP.get(method)
    resp_cls = _RESP_MAP.get(method)
    if req_cls is None or resp_cls is None:
        print(f"错误：不支持的 method：{method}", file=sys.stderr)
        return 1
    try:
        async with SocketClient(port=port) as client:
            result = await client.call(req_cls())
    except RpcConnectionError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        print("提示：kwok-server 可能未运行，请先启动 `kwok server start`。", file=sys.stderr)
        return 1
    except RpcError as exc:
        print(f"错误（{exc.code}）：{exc.message}", file=sys.stderr)
        return 1

    try:
        resp = resp_cls.model_validate(result)
    except ValidationError as exc:
        print(f"错误：server 返回了无法识别的响应体：{exc}", file=sys.stderr)
        return 1
    print_formatter(resp, start_time)
    return 0