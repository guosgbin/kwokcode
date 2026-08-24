from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable

from kwok.protocol.errors import LlmError
from kwok.protocol.events import ToolCallFinishEvent, ToolCallStartEvent
from kwok.server.llm.llm_context import LlmContext
from kwok.server.llm.model import ToolCall
from kwok.server.middleware import Middleware
from kwok.server.tools import get_tool_registry

logger = logging.getLogger(__name__)


class ToolEventPushMiddleware(Middleware):
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


class ToolParamCheckMiddleware(Middleware):
    tool_order: int = 5

    async def around_tool(
            self,
            ctx: LlmContext,
            call: ToolCall,
            next_call: Callable[[], Awaitable[str]],
    ) -> str:
        logger.info(f"哈哈哈哈，工具调用：{call.name}")
        # 校验入参
        tool = get_tool_registry().get(call.name)
        if tool is None:
            raise LlmError(f"未知工具：{call.name}")
        call.resolved_tool = tool

        # 解析 + 校验参数
        try:
            args = json.loads(call.arguments or "{}")
        except json.JSONDecodeError as exc:
            return f"工具参数解析失败：{exc}"

        if tool.input_model is None:
            return f"工具 {call.name} 缺少 input_model"

        try:
            validated = tool.input_model.model_validate(args)
        except Exception as exc:
            return f"工具参数校验失败：{exc}"

        call.validated_args = validated.model_dump()
        result = await next_call()
        return result
