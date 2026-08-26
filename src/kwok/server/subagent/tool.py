"""subagent 工具集：``spawn_agent`` / ``agent_result`` / ``cancel_task``。

三个工具均为元操作（``permission_level=ALLOW``，免权限弹窗）；子 agent 内写工具
的权限审批仍走全局 ``PermissionManager``（FR-019，勿绕过权限链）。
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from kwok.server.subagent.loader import AgentLoader
from kwok.server.subagent.registry import BackgroundTask, BackgroundTaskRegistry
from kwok.server.subagent.runner import run_child
from kwok.server.tools.context import cwd_var
from kwok.server.tools.runner import agent_ctx_var
from kwok.server.tools.tool import PermissionLevel, RiskLevel, Tool
from kwok.util.id_generator import gen_turn_id

if TYPE_CHECKING:
    from kwok.server.llm.provider.llm_provider import LlmProvider


class SpawnAgentInput(BaseModel):
    description: str
    prompt: str
    run_in_background: bool = False
    subagent_type: str = "implementer"


class SpawnAgentTool(Tool):
    name = "spawn_agent"
    description = (
        "派生一个隔离的子 agent 执行子任务：前台阻塞等待结果，"
        "后台立即返回 turn_id 供 agent_result 查询 / cancel_task 取消"
    )
    input_model = SpawnAgentInput
    permission_level = PermissionLevel.ALLOW
    risk_level = RiskLevel.MEDIUM

    def __init__(self, provider: LlmProvider, registry: BackgroundTaskRegistry) -> None:
        self._provider = provider
        self._registry = registry

    def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("spawn_agent 需在事件循环内执行（execute_async）")

    async def execute_async(self, args: dict[str, Any]) -> dict[str, Any]:
        parent_ctx = agent_ctx_var.get()
        if parent_ctx is None:
            return {"status": "error", "error": "spawn_agent 缺少执行上下文"}
        # 嵌套防护（FR 最多一层嵌套）：子上下文（tool_registry 非空）内禁止再 spawn
        if parent_ctx.tool_registry is not None:
            return {"status": "error", "error": "最多一层嵌套：子 agent 内禁止再次 spawn_agent"}
        inp = SpawnAgentInput(**args)
        role = AgentLoader().resolve(inp.subagent_type, cwd_var.get() or ".")
        if role is None:
            return {"status": "error", "error": f"未找到角色：{inp.subagent_type}"}
        child_turn_id = gen_turn_id()
        if inp.run_in_background:
            task = asyncio.create_task(
                run_child(
                    parent_ctx, role, child_turn_id, inp.prompt, inp.description, self._provider
                )
            )
            self._registry.register(
                BackgroundTask(
                    turn_id=child_turn_id,
                    task=task,
                    owner_session_id=parent_ctx.session_id,
                )
            )
            return {"status": "started", "turn_id": child_turn_id}
        result = await run_child(
            parent_ctx, role, child_turn_id, inp.prompt, inp.description, self._provider
        )
        return {
            "turn_id": result.turn_id,
            "status": result.status,
            "result": result.text,
            "error": result.error,
        }


class AgentResultInput(BaseModel):
    turn_id: str


class AgentResultTool(Tool):
    name = "agent_result"
    description = "查询后台子 agent 任务状态：running / cancelled / exception / result"
    input_model = AgentResultInput
    permission_level = PermissionLevel.ALLOW

    def __init__(self, registry: BackgroundTaskRegistry) -> None:
        self._registry = registry

    def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("agent_result 需在事件循环内执行（execute_async）")

    async def execute_async(self, args: dict[str, Any]) -> dict[str, Any]:
        inp = AgentResultInput(**args)
        task = self._registry.get(inp.turn_id)
        if task is None:
            return {"status": "unknown", "turn_id": inp.turn_id, "error": "未知任务 turn_id"}
        state = task.state
        if state == "running":
            return {"status": "running", "turn_id": inp.turn_id}
        if state == "cancelled":
            return {"status": "cancelled", "turn_id": inp.turn_id}
        if state == "failed":
            exc = task.task.exception()
            if exc is not None:
                return {"status": "exception", "turn_id": inp.turn_id, "error": str(exc)}
            result = task.task.result()
            return {
                "status": "exception",
                "turn_id": inp.turn_id,
                "error": result.error or "子任务失败",
            }
        result = task.task.result()
        return {"status": "result", "turn_id": inp.turn_id, "result": result.text}


class CancelTaskInput(BaseModel):
    turn_id: str


class CancelTaskTool(Tool):
    name = "cancel_task"
    description = "显式取消后台子 agent 任务；已完成/不存在为安全 no-op"
    input_model = CancelTaskInput
    permission_level = PermissionLevel.ALLOW

    def __init__(self, registry: BackgroundTaskRegistry) -> None:
        self._registry = registry

    def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("cancel_task 需在事件循环内执行（execute_async）")

    async def execute_async(self, args: dict[str, Any]) -> dict[str, Any]:
        inp = CancelTaskInput(**args)
        cancelled = self._registry.cancel(inp.turn_id)
        task = self._registry.get(inp.turn_id)
        return {
            "turn_id": inp.turn_id,
            "cancelled": cancelled,
            "state": task.state if task is not None else None,
        }
