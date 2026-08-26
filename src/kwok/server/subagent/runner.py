"""子 agent 运行层：角色 → 子注册表（白名单物理限制）→ 子 LLM 循环。

前台（SpawnAgentTool 阻塞等待）/ 后台（BackgroundTaskRegistry 注册）共用
``run_child``；角色工具白名单在此收敛为**只含白名单工具的独立注册表**，
挂到子 LlmContext.tool_registry 后，工具解析与权限判定全部以 ctx 为准（fail-closed）。

子执行隔离（宪法 III 事件外化）：
    - 子 bus（独立 EventBusManager）承载子事件，``TurnLogWriterBus`` 落盘
      ``<session>/turns/<child_turn_id>/event.jsonl``（独立于父 turn 日志）。
    - ``_bridge`` 把子事件转发父 bus，供 TUI/订阅者消费；父 writer 按 turn_id 过滤，
      子事件不会污染父 event.jsonl。
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from kwok.protocol.events import BaseEvent, SubagentFinishedEvent, SubagentStartedEvent
from kwok.server.event import EventBusManager, get_bus
from kwok.server.event.turn_log_writer_bus import TurnLogWriterBus
from kwok.server.llm.llm_context import LlmContext
from kwok.server.llm.loop import run_llm_loop
from kwok.server.subagent.parser import AgentRole
from kwok.server.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from kwok.server.llm.provider.llm_provider import LlmProvider

logger = logging.getLogger(__name__)

ChildStatus = Literal["success", "failed", "cancelled"]


@dataclass
class ChildResult:
    """一次子 agent 执行的终态结果。"""

    turn_id: str
    status: ChildStatus
    text: str = ""
    error: str | None = None


async def _bridge(event: BaseEvent) -> None:
    """子事件转发父（全局）bus；父订阅者异常不影响子执行（静默跳过）。"""
    try:
        await get_bus().publish(event)
    except Exception:
        logger.exception("子事件转发失败 type=%s", event.type)


def _build_child_registry(role: AgentRole) -> ToolRegistry:
    """按角色工具白名单构建子注册表。

    - 白名单内未注册的工具（名称未知/拼写错）跳过并告警。
    - 空白名单 → 空注册表（fail-closed：子 agent 无任何工具可用）。
    """
    from kwok.server.tools import get_tool_registry

    global_registry = get_tool_registry()
    child = ToolRegistry()
    for name in role.tools:
        tool = global_registry.get(name)
        if tool is None:
            logger.warning("角色 %s 白名单含未知工具 %r，已跳过", role.name, name)
            continue
        child.register(tool)
    return child


async def run_child(
    parent_ctx: LlmContext,
    role: AgentRole,
    child_turn_id: str,
    instruction: str,
    description: str = "",
    provider: LlmProvider | None = None,
) -> ChildResult:
    """前台/后台共用的子 agent 执行入口：冷启动隔离 + 子注册表 + 独立 bus/落盘。

    - 子 LlmContext：``tool_registry``=子注册表（白名单物理限制，依赖 T004）、
      ``skill_prompt``=角色正文（替换 base，冷启动）、messages 仅含本次指令，
      不注入 memory / 不压缩（context_pct=0 天然低于压缩阈值）。
    - 生命周期：父 bus 发 ``SubagentStartedEvent`` → ``run_llm_loop`` →
      ``SubagentFinishedEvent``（取消/异常同样保证 FINISHED 送达）。
    """
    child_bus = EventBusManager()
    child_base = (
        Path(parent_ctx.session_dir) / "turns" if parent_ctx.session_dir else None
    )
    writer = TurnLogWriterBus(turn_id=child_turn_id, base_dir=child_base)
    child_bus.subscribe(writer.on_event)
    child_bus.subscribe(_bridge)

    from kwok.server.subagent import get_provider

    provider_obj = provider or get_provider()
    child_registry = _build_child_registry(role)
    context = LlmContext(
        turn_id=child_turn_id,
        prompt=instruction,
        bus=child_bus,
        max_steps=parent_ctx.max_steps,
        messages=[{"role": "user", "content": instruction}],
        tools=child_registry.schemas(),
        session_id=parent_ctx.session_id,
        skill_prompt=role.system_prompt,
        session_dir=parent_ctx.session_dir,
        tool_registry=child_registry,
    )

    await get_bus().publish(
        SubagentStartedEvent(
            child_turn_id=child_turn_id,
            parent_turn_id=parent_ctx.turn_id,
            description=description or instruction,
        )
    )
    status: ChildStatus = "success"
    error: str | None = None
    try:
        try:
            await run_llm_loop(provider_obj, context)
        except asyncio.CancelledError:
            status = "cancelled"
            raise
        except Exception as exc:
            status = "failed"
            error = str(exc)
            logger.exception("子 agent 运行异常 child_turn_id=%s", child_turn_id)
        else:
            if context.status == "failed":
                status = "failed"
                error = context.reason
    finally:
        try:
            await get_bus().publish(
                SubagentFinishedEvent(
                    child_turn_id=child_turn_id,
                    parent_turn_id=parent_ctx.turn_id,
                    status=status,
                )
            )
        finally:
            child_bus.unsubscribe(writer.on_event)
            child_bus.unsubscribe(_bridge)
            writer.close()
    return ChildResult(
        turn_id=child_turn_id, status=status, text=context.text, error=error
    )
