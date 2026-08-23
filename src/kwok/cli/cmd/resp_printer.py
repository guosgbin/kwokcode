import time
from typing import Any

from kwok.protocol.rpc_model import (
    PingJsonRpcResp,
    PromptResp,
    SubscribeResp,
    UnsubscribeResp,
    VersionJsonRpcResp,
)


def print_formatter(resp: Any, start_time: float | None = None) -> None:
    if isinstance(resp, PingJsonRpcResp):
        latency = (
            f" latency={int((time.monotonic() - start_time) * 1000)}ms"
            if start_time is not None
            else ""
        )
        print(
            f"pong\nserver_version={resp.server_version} "
            f"uptime={resp.uptime_ms}ms{latency}"
        )
    elif isinstance(resp, VersionJsonRpcResp):
        print(resp.version)
    elif isinstance(resp, PromptResp):
        print(resp)
    elif isinstance(resp, SubscribeResp):
        print(resp)
    elif isinstance(resp, UnsubscribeResp):
        print(resp)
