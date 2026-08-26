"""Subagent 多 agent 协作域：角色配置层 + 运行时层。

主 agent 经 ``spawn_agent`` 派生出**冷启动隔离**的子 agent（前台阻塞 / 后台注册），
子事件经 ``_bridge`` 转发父 bus、子 events 独立落盘（``turns/<child_turn_id>/event.jsonl``）。

消费方统一从这里 import：
    from kwok.server.subagent import get_task_registry, init_subagent_system
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kwok.server.llm.llm_context import LlmContext as LlmContext
    from kwok.server.llm.provider.llm_provider import LlmProvider as LlmProvider
    from kwok.server.subagent.registry import (
        BackgroundTaskRegistry as BackgroundTaskRegistry,
    )
    from kwok.server.subagent.tool import (
        AgentResultTool as AgentResultTool,
    )
    from kwok.server.subagent.tool import (
        CancelTaskTool as CancelTaskTool,
    )
    from kwok.server.subagent.tool import (
        SpawnAgentTool as SpawnAgentTool,
    )

_registry: BackgroundTaskRegistry | None = None
_provider: LlmProvider | None = None


def get_task_registry() -> BackgroundTaskRegistry:
    """进程级后台任务注册表（server 生命周期 = 跨 session/多轮对话共享）。"""
    if _registry is None:
        raise RuntimeError(
            "BackgroundTaskRegistry 未初始化，请先调用 init_subagent_system"
        )
    return _registry


def get_provider() -> LlmProvider:
    """进程级 LLM provider（子 agent 执行引擎复用）。"""
    if _provider is None:
        raise RuntimeError("LlmProvider 未初始化，请先调用 init_subagent_system")
    return _provider


def init_subagent_system(provider: LlmProvider) -> None:
    """server 启动时调用一次：创建注册表单例 + 注册三个 subagent 工具。幂等。

    - SpawnAgentTool：spawn 入口（前台阻塞 / 后台注册）
    - AgentResultTool：后台任务查询（still running → cancelled → exception → result）
    - CancelTaskTool：显式取消后台子任务
    """
    global _registry, _provider
    if _registry is not None:
        return
    from kwok.server.subagent.registry import BackgroundTaskRegistry
    from kwok.server.subagent.tool import (
        AgentResultTool,
        CancelTaskTool,
        SpawnAgentTool,
    )
    from kwok.server.tools import get_tool_registry

    _provider = provider
    _registry = BackgroundTaskRegistry()
    reg = get_tool_registry()
    reg.register(SpawnAgentTool(provider, _registry))
    reg.register(AgentResultTool(_registry))
    reg.register(CancelTaskTool(_registry))
