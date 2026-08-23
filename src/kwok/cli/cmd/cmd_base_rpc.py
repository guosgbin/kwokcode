import sys
import time

from pydantic import ValidationError

from kwok.cli.cmd.resp_printer import print_formatter
from kwok.net.client import SocketClient
from kwok.protocol.errors import RpcConnectionError, RpcError
from kwok.protocol.messages import RESP_ADAPTER, build_request


async def run(method: str, port: int) -> int:
    start_time = time.monotonic()
    req = build_request(method)
    params = req.model_dump(mode="json") if req is not None else None
    try:
        async with SocketClient(port=port) as client:
            result = await client.call(method, params=params)
    except RpcConnectionError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        print("提示：kwok-server 可能未运行，请先启动 `kwok-server`。", file=sys.stderr)
        return 1
    except RpcError as exc:
        print(f"错误（{exc.code}）：{exc.message}", file=sys.stderr)
        return 1

    try:
        resp = RESP_ADAPTER.validate_python(result)
    except ValidationError as exc:
        print(f"错误：server 返回了无法识别的响应体：{exc}", file=sys.stderr)
        return 1
    print_formatter(resp, start_time)
    return 0
