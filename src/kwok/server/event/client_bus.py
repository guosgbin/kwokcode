from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from kwok.protocol.context import connection_id_var
from kwok.protocol.events import BaseEvent, EventType
from kwok.protocol.topics import match

logger = logging.getLogger(__name__)

# 连接上下文之外发布、仍需广播给所有订阅者的全局事件类型。
# 会话事件必须在连接上下文内发布；否则视为异常丢弃（fail-safe，避免静默广播）。
_GLOBAL_EVENT_TYPES: frozenset[EventType] = frozenset({EventType.SERVER_STATUS})

SendEvent = Callable[[str, dict[str, Any]], Awaitable[None]]


class ClientEventPush:

    def __init__(self) -> None:

        self._patterns: dict[str, set[str]] = {}

        self._senders: dict[str, SendEvent] = {}

    def attach(self, connection_id: str, sender: SendEvent) -> None:

        self._senders[connection_id] = sender
        self._patterns.setdefault(connection_id, set())

    def detach(self, connection_id: str) -> None:

        self._patterns.pop(connection_id, None)
        self._senders.pop(connection_id, None)

    def subscribe(self, connection_id: str, patterns: list[str]) -> None:

        conn_patterns = self._patterns.setdefault(connection_id, set())
        conn_patterns.update(patterns)

    def unsubscribe(self, connection_id: str, patterns: list[str]) -> list[str]:

        conn_patterns = self._patterns.get(connection_id)
        if conn_patterns is None:
            return []
        removed = [p for p in patterns if p in conn_patterns]
        conn_patterns.difference_update(patterns)
        return removed

    async def publish(self, event: BaseEvent) -> None:
        """事件投递：连接上下文内的会话事件只投给该连接；其余全局事件广播。

        连接上下文由 SocketServer 在连接建立时设置并随 task 拷贝传播，因此每个
        turn 的事件只到达其 owner 连接，跨会话不再串扰（会话隔离）。
        """
        conn_id = connection_id_var.get()
        if conn_id is not None:
            await self._deliver(conn_id, event)
            return
        if event.type not in _GLOBAL_EVENT_TYPES:
            logger.warning(
                "事件在连接上下文外发布且非全局类型，已丢弃 type=%s", event.type
            )
            return
        for connection_id, patterns in self._patterns.items():
            if not any(match(pattern, event.type) for pattern in patterns):
                continue
            await self._deliver(connection_id, event)

    async def _deliver(self, connection_id: str, event: BaseEvent) -> None:
        """向单个连接投递事件：订阅模式匹配 + sender 存在才发，异常不向上抛。"""
        patterns = self._patterns.get(connection_id)
        if patterns is None or not any(match(pattern, event.type) for pattern in patterns):
            return
        sender = self._senders.get(connection_id)
        if sender is None:
            return
        try:
            await sender(event.type, event.model_dump())
        except Exception:
            logger.exception(
                "事件投递失败 conn=%s type=%s", connection_id, event.type
            )
