from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from kwok.server.llm.model import LlmResponse, ToolCall

if TYPE_CHECKING:
    from kwok.server.llm.llm_context import LlmContext


class Middleware:
    model_order: int = 500
    tool_order: int = 500

    async def around_model(
        self,
        ctx: LlmContext,
        next_call: Callable[[], Awaitable[LlmResponse]],
    ) -> LlmResponse:
        await self._before_model(ctx)
        resp = await next_call()
        await self._after_model(ctx, resp)
        return resp

    async def around_tool(
        self,
        ctx: LlmContext,
        call: ToolCall,
        next_call: Callable[[], Awaitable[str]],
    ) -> str:
        await self._before_tool(ctx, call)
        result = await next_call()
        await self._after_tool(ctx, call, result)
        return result

    async def _before_model(self, ctx: LlmContext) -> None: ...

    async def _after_model(self, ctx: LlmContext, resp: LlmResponse) -> None: ...

    async def _before_tool(self, ctx: LlmContext, call: ToolCall) -> None: ...

    async def _after_tool(self, ctx: LlmContext, call: ToolCall, result: str) -> None: ...