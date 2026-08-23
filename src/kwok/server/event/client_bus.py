from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from kwok.protocol.events import BaseEvent
from kwok.protocol.topics import match

logger = logging.getLogger(__name__)

SendEvent = Callable[[str, dict[str, Any]], Awaitable[None]]


class ClientEventPush:

    def __init__(self) -> None:

        self._types: set[str] = set()

        self._patterns: dict[str, set[str]] = {}

        self._senders: dict[str, SendEvent] = {}

    def register(self, event_type: str) -> None:

        self._types.add(event_type)

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

    def types(self) -> list[str]:

        return sorted(self._types)

    async def publish(self, event: BaseEvent) -> None:

        for connection_id, patterns in self._patterns.items():
            if not any(match(pattern, event.type) for pattern in patterns):
                continue
            sender = self._senders.get(connection_id)
            if sender is None:
                continue
            try:
                await sender(event.type, event.model_dump())
            except Exception:
                logger.exception(
                    "事件投递失败 conn=%s type=%s", connection_id, event.type
                )
