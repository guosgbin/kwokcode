from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from kwok.protocol.errors import LlmError
from kwok.protocol.events import ToolCallFinishEvent, ToolCallStartEvent
from kwok.server.llm.llm_context import LlmContext
from kwok.server.llm.model import ToolCall
from kwok.server.middleware import Middleware

logger = logging.getLogger(__name__)


class ToolEventMiddleware(Middleware):
    model_order: int = 500
    tool_order: int = 0

    async def around_tool(
        self,
        ctx: LlmContext,
        call: ToolCall,
        next_call: Callable[[], Awaitable[str]],
    ) -> str:
        await ctx.bus.publish(
            ToolCallStartEvent(
                turn_id=ctx.turn_id,
                step_id=ctx.step,
                tool_call_id=call.id,
                name=call.name,
                arguments=call.arguments,
            )
        )
        try:
            result = await next_call()
        except LlmError:
            raise
        except Exception as exc:
            error_msg = f"工具执行异常：{exc}"
            await ctx.bus.publish(
                ToolCallFinishEvent(
                    turn_id=ctx.turn_id,
                    step_id=ctx.step,
                    tool_call_id=call.id,
                    name=call.name,
                    result=error_msg,
                )
            )
            raise
        await ctx.bus.publish(
            ToolCallFinishEvent(
                turn_id=ctx.turn_id,
                step_id=ctx.step,
                tool_call_id=call.id,
                name=call.name,
                result=result,
            )
        )
        return result