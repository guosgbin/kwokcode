"""事件系统注册中心：进程级单例的受控访问点。

Python 模块天然是进程级单例（sys.modules 缓存），这里把事件总线和客户端
推送收敛成模块级持有 + 显式初始化，替代构造参数传递链。只暴露四个函数：
初始化（幂等）、两个 getter、测试隔离用的 reset。
"""

from __future__ import annotations

from kwok.server.event.client_bus import ClientEventPush
from kwok.server.event.manager import EventBusManager

_bus: EventBusManager | None = None
_client_push: ClientEventPush | None = None


def init_event_system() -> tuple[EventBusManager, ClientEventPush]:
    """幂等初始化事件系统并接线：事件总线 → 客户端推送。返回 (bus, client_push)。"""
    global _bus, _client_push
    if _bus is not None and _client_push is not None:
        return _bus, _client_push
    bus = EventBusManager()
    client_push = ClientEventPush()
    bus.subscribe(client_push.publish)
    _bus = bus
    _client_push = client_push
    return bus, client_push


def get_bus() -> EventBusManager:
    """取进程级事件总线（未初始化则抛错）。"""
    if _bus is None:
        raise RuntimeError("事件系统未初始化：请先调用 setup_event_system()")
    return _bus


def get_client_push() -> ClientEventPush:
    """取进程级客户端事件推送（未初始化则抛错）。"""
    if _client_push is None:
        raise RuntimeError("事件系统未初始化：请先调用 setup_event_system()")
    return _client_push
