from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

from kwok.protocol.errors import LlmError
from kwok.server.llm.model import ToolCall
from kwok.server.middleware import get_middleware_chain
from kwok.server.tools.tool import _REGISTRY, ToolImpl

if TYPE_CHECKING:
    from kwok.server.llm.llm_context import LlmContext


class ToolRunner:
    def __init__(
        self,
        *,
        registry: dict[str, ToolImpl] | None = None,
    ) -> None:
        self._registry = registry

    async def execute(self, call: ToolCall, ctx: LlmContext) -> str:
        async def _core() -> str:
            tool = (
                _REGISTRY.get(call.name)
                if self._registry is None
                else self._registry.get(call.name)
            )
            if tool is None:
                raise LlmError(f"未知工具：{call.name}")
            try:
                args = json.loads(call.arguments or "{}")
            except json.JSONDecodeError as exc:
                return f"工具参数解析失败：{exc}"
            return await asyncio.to_thread(tool.execute, args)

        return await get_middleware_chain().invoke_around_tool(ctx, call, _core)