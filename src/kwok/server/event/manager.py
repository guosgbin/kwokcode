from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from kwok.protocol.events import BaseEvent

logger = logging.getLogger(__name__)

type EventHandler = Callable[[BaseEvent], Awaitable[None]]


class EventBusManager:
    def __init__(self) -> None:
        self._subscribers: list[EventHandler] = []

    def subscribe(self, handler: EventHandler) -> None:
        self._subscribers.append(handler)

    async def publish(self, event: BaseEvent) -> None:
        for handler in self._subscribers:
            try:
                await handler(event)
            except Exception:
                logger.exception("订阅者处理事件异常 type=%s", event.type)
