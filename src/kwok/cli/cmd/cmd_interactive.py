from __future__ import annotations

import asyncio
import os
import readline  # noqa: F401 — 启用 input() 的行编辑，中文退格才按字符删除
import sys

from kwok.cli.event_handlers.event_handlers import event_mgr
from kwok.net.client import SocketClient
from kwok.protocol.errors import RpcConnectionError, RpcError
from kwok.protocol.events import BaseEvent, EventType
from kwok.protocol.rpc_model import (
    SessionCloseReq,
    SessionCreateReq,
    SessionPromptReq,
    SubscribeReq,
)


async def run_interactive(port: int, timeout: float) -> int:
    turn_finished = asyncio.Event()
    exit_code = 0

    async def on_event(event: BaseEvent) -> None:
        nonlocal exit_code
        await event_mgr.dispatch(event)
        if event.type == EventType.TURN_FINISH:
            turn_finished.set()
        elif event.type == EventType.TURN_ERROR:
            exit_code = 1
            turn_finished.set()

    try:
        async with SocketClient(port=port, timeout=timeout) as client:
            client.on_event(on_event)

            await client.call(SubscribeReq(patterns=["llm.*", "turn.*", "step.*", "tool.**"]))

            result = await client.call(SessionCreateReq(cwd=os.getcwd()))
            session_id = result["session_id"]
            print(f"会话已创建：{session_id}\n")

            while True:
                prompt = await _readline()
                if prompt is None:
                    break
                if not prompt:
                    continue
                if prompt.startswith("/"):
                    if _handle_command(prompt):
                        break
                    continue

                turn_finished.clear()
                try:
                    await client.call(SessionPromptReq(prompt=prompt, session_id=session_id))
                except RpcError as exc:
                    print(f"\n错误（{exc.code}）：{exc.message}")
                    continue

                await turn_finished.wait()

            if session_id is not None:
                await client.call(SessionCloseReq(session_id=session_id))

    except RpcConnectionError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        print("提示：kwok-server 可能未运行，请先启动 `kwok server start`。", file=sys.stderr)
        return 1

    return exit_code


async def _readline() -> str | None:
    try:
        return await asyncio.to_thread(input, ">>> ")
    except (EOFError, KeyboardInterrupt):
        print()
        return None


def _handle_command(cmd: str) -> bool:
    cmd = cmd.strip().lower()
    if cmd == "/exit":
        return True
    if cmd == "/help":
        print(
            "可用命令：\n"
            "  /exit    退出\n"
            "  /help    显示帮助\n"
            "  /clear   清屏"
        )
        return False
    if cmd == "/clear":
        print("\033[2J\033[H", end="")
        return False
    print(f"未知命令：{cmd}")
    return False