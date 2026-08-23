from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from kwok.protocol.errors import LlmError
from kwok.protocol.events import ToolCallFinishEvent, ToolCallStartEvent
from kwok.server.llm.llm_context import LlmContext
from kwok.server.llm.model import ToolCall

ToolImpl = Callable[[dict[str, Any]], str]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    execute: ToolImpl
    strict: bool = True

    @property
    def schema(self) -> dict[str, object]:

        params = dict(self.parameters)
        if self.strict:
            params.setdefault("additionalProperties", False)
        function: dict[str, object] = {
            "name": self.name,
            "description": self.description,
            "parameters": params,
        }
        if self.strict:
            function["strict"] = True
        return {"type": "function", "function": function}


_REGISTRY: dict[str, Tool] = {}


def register(tool: Tool) -> None:
    _REGISTRY[tool.name] = tool


async def execute_tool(call: ToolCall, context: LlmContext | None = None) -> str:
    if context is not None:
        await context.bus.publish(
            ToolCallStartEvent(
                turn_id=context.turn_id,
                step_id=context.step,
                tool_call_id=call.id,
                name=call.name,
            )
        )
    tool = _REGISTRY.get(call.name)
    if tool is None:
        raise LlmError(f"未知工具：{call.name}")
    try:
        args = json.loads(call.arguments or "{}")
    except json.JSONDecodeError as exc:
        return f"工具参数解析失败：{exc}"
    result = await asyncio.to_thread(tool.execute, args)
    if context is not None:
        await context.bus.publish(
            ToolCallFinishEvent(
                turn_id=context.turn_id,
                step_id=context.step,
                tool_call_id=call.id,
                name=call.name,
                result=result,
            )
        )
    return result
