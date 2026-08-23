import asyncio
import sys
from typing import Any

from kwok.cli.event_handlers.event_handlers import event_mgr
from kwok.cli.cmd.resp_printer import print_formatter
from kwok.net.client import SocketClient
from kwok.protocol.enums import Method
from kwok.protocol.errors import RpcConnectionError, RpcError
from kwok.protocol.events import EventType
from kwok.protocol.messages import RESP_ADAPTER


async def run_prompt(prompt: str, port: int, timeout: float) -> int:
    finished = asyncio.Event()
    exit_code = 0

    async def on_event(event: Any) -> None:
        nonlocal exit_code
        await event_mgr.dispatch(event)
        if event.type == EventType.TURN_FINISH:
            finished.set()
        elif event.type == EventType.TURN_ERROR:
            exit_code = 1
            finished.set()

    try:
        async with SocketClient(port=port, timeout=timeout) as client:
            client.on_event(on_event)

            eventSubscribeResp = await client.call(
                Method.EVENT_SUBSCRIBE, {"patterns": ["llm.*", "turn.*", "step.*", "tool.**"]}
            )
            print_formatter(RESP_ADAPTER.validate_python(eventSubscribeResp))
            try:

                chatResp = await client.call(Method.CHAT, {"prompt": prompt})
                print_formatter(RESP_ADAPTER.validate_python(chatResp))
            except RpcError as exc:
                print(f"错误（{exc.code}）：{exc.message}", file=sys.stderr)
                return 1
            await finished.wait()
    except RpcConnectionError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        print("提示：kwok-server 可能未运行，请先启动 `kwok-server`。", file=sys.stderr)
        return 1
    return exit_code
