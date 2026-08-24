from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from kwok.server.llm.model import LlmResponse, ToolCall

if TYPE_CHECKING:
    from kwok.server.llm.llm_context import LlmContext

from kwok.server.middleware.middleware import Middleware


class MiddlewareChain:
    def __init__(self) -> None:
        self._middleware: list[Middleware] = []

    def add(self, mw: Middleware) -> None:
        if mw in self._middleware:
            return
        self._middleware.append(mw)

    def remove(self, mw_type: type[Middleware]) -> None:
        for mw in self._middleware:
            if type(mw) is mw_type:
                self._middleware.remove(mw)
                return

    async def invoke_around_model(
        self,
        ctx: LlmContext,
        core_call: Callable[[], Awaitable[LlmResponse]],
    ) -> LlmResponse:
        sorted_mw = sorted(self._middleware, key=lambda m: m.model_order)

        async def handler(idx: int) -> LlmResponse:
            if idx == len(sorted_mw):
                return await core_call()
            return await sorted_mw[idx].around_model(ctx, lambda: handler(idx + 1))

        return await handler(0)

    async def invoke_around_tool(
        self,
        ctx: LlmContext,
        call: ToolCall,
        core_call: Callable[[], Awaitable[str]],
    ) -> str:
        sorted_mw = sorted(self._middleware, key=lambda m: m.tool_order)

        async def handler(idx: int) -> str:
            if idx == len(sorted_mw):
                return await core_call()
            return await sorted_mw[idx].around_tool(ctx, call, lambda: handler(idx + 1))

        return await handler(0)


def _init_middleware_chain(chain: MiddlewareChain) -> None:
    from kwok.server.middleware.prebuilt.tool_middleware import (
        ToolEventPushMiddleware,
        ToolParamCheckMiddleware,
    )

    chain.add(ToolEventPushMiddleware())
    chain.add(ToolParamCheckMiddleware())