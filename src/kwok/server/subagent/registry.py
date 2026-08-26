"""后台子任务注册表：进程级单例（跨 session/多轮共享），断连级联取消锚点。

- ``BackgroundTask`` 记录 turn_id / asyncio.Task / 归属 session；state 从 task 现算。
- 已完成任务保留在注册表（agent_result 仍可查结果），不做自动回收。
- ``cancel_by_session`` 供 app._on_disconnect 断连级联取消（FR-021）。
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from kwok.server.subagent.runner import ChildResult

TaskState = Literal["running", "success", "failed", "cancelled"]


@dataclass
class BackgroundTask:
    """一个后台子 agent 任务：注册表条目 + 状态现算。"""

    turn_id: str
    task: asyncio.Task[ChildResult]
    owner_session_id: str

    @property
    def state(self) -> TaskState:
        """从 task 现算状态：运行中 / 成功 / 失败 / 已取消。"""
        if not self.task.done():
            return "running"
        if self.task.cancelled():
            return "cancelled"
        exc = self.task.exception()
        if exc is not None:
            return "failed"
        return self.task.result().status


class BackgroundTaskRegistry:
    """进程级后台任务注册表。模块单例由 ``init_subagent_system`` 创建。"""

    def __init__(self) -> None:
        self._tasks: dict[str, BackgroundTask] = {}

    def register(self, task: BackgroundTask) -> None:
        if task.turn_id in self._tasks:
            raise ValueError(f"后台任务已存在：{task.turn_id}")
        self._tasks[task.turn_id] = task

    def get(self, turn_id: str) -> BackgroundTask | None:
        return self._tasks.get(turn_id)

    def all(self) -> list[BackgroundTask]:
        return list(self._tasks.values())

    def cancel(self, turn_id: str) -> bool:
        """取消指定任务；已完成/不存在安全 no-op，返回是否实际发起取消。"""
        task = self._tasks.get(turn_id)
        if task is None or task.task.done():
            return False
        task.task.cancel()
        return True

    def cancel_by_session(self, session_ids: list[str]) -> int:
        """断连级联取消：取消这些 session 拥有且仍在运行的全部任务，返回取消数。"""
        count = 0
        for task in list(self._tasks.values()):
            if task.owner_session_id in session_ids and not task.task.done():
                task.task.cancel()
                count += 1
        return count
