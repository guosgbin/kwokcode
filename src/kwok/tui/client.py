from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, cast

from kwok.config import get_config
from kwok.net.client import SocketClient
from kwok.protocol.enums import PermissionDecision
from kwok.protocol.events import BaseEvent
from kwok.protocol.rpc_model import (
    PermissionRespondReq,
    PromptResp,
    SessionCloseReq,
    SessionCompactReq,
    SessionCompactResp,
    SessionCreateReq,
    SessionCreateResp,
    SessionPromptReq,
)


class TuiClient:
    """kwok-tui 的会话/事件客户端：封装 SocketClient，面向界面层的窄接口。

    连接失败、RPC 错误统一向上抛（RpcConnectionError / RpcError），由 App 层转可读提示。
    """

    def __init__(self, client: SocketClient | None = None) -> None:
        self._client = client if client is not None else SocketClient()
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        await self._client.connect()
        self._connected = True

    async def subscribe(self, patterns: list[str]) -> tuple[str, AsyncIterator[BaseEvent]]:
        """订阅事件模式，返回 (connection_id, 事件异步迭代器)。"""
        connection_id, events = await self._client.subscribe(patterns)
        return connection_id, _typed_events(events)

    async def create_session(self, cwd: str) -> str:
        resp = SessionCreateResp.model_validate(
            await self._client.call(SessionCreateReq(cwd=cwd))
        )
        return resp.session_id

    async def prompt(self, prompt: str, session_id: str) -> str:
        resp = PromptResp.model_validate(
            await self._client.call(SessionPromptReq(prompt=prompt, session_id=session_id))
        )
        return resp.turn_id

    async def close_session(self, session_id: str) -> None:
        await self._client.call(SessionCloseReq(session_id=session_id))

    async def compact(self, session_id: str) -> SessionCompactResp:
        # 压缩是慢 RPC：服务端要跑一次 LLM 摘要调用（受 llm.timeout 约束），
        # 不套用默认 3s 的 socket 超时，否则 /compact 秒级误报"等待响应超时"。
        wait = get_config().llm.timeout + 60
        resp = SessionCompactResp.model_validate(
            await self._client.call(
                SessionCompactReq(session_id=session_id), timeout=wait
            )
        )
        return resp

    async def send_permission_respond(
            self, tool_use_id: str, decision: PermissionDecision
    ) -> None:
        await self._client.call(
            PermissionRespondReq(tool_use_id=tool_use_id, decision=decision)
        )

    async def close(self) -> None:
        await self._client.close()
        self._connected = False


async def _typed_events(events: AsyncIterator[Any]) -> AsyncIterator[BaseEvent]:
    """把 SocketClient 的 Any 事件流收窄为 BaseEvent（运行时已由 EVENT_ADAPTER 解析）。"""
    async for event in events:
        yield cast(BaseEvent, event)


__all__ = ["TuiClient"]
