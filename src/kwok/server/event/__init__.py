"""事件域公共入口：注册中心 + 两个核心组件。

消费方统一从这里 import，不再深入子模块：
    from kwok.server.event import get_bus, get_client_push
"""

from kwok.server.event.client_bus import ClientEventPush
from kwok.server.event.manager import EventBusManager
from kwok.server.event.registry import (
    get_bus,
    get_client_push,
    init_event_system,
)

__all__ = [
    "ClientEventPush",
    "EventBusManager",
    "get_bus",
    "get_client_push",
    "init_event_system",
]
