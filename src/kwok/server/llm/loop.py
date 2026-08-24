from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from kwok.config import get_config
from kwok.protocol.enums import ErrorCode
from kwok.protocol.errors import LlmError
from kwok.protocol.events import (
    StepFinishEvent,
    StepStartEvent,
    TurnErrorEvent,
    TurnFinishEvent,
    TurnStartEvent,
)
from kwok.server.event import get_bus
from kwok.server.event.turn_log_writer_bus import TurnLogWriterBus
from kwok.server.llm.llm_context import LlmContext
from kwok.server.llm.model import AssistantMessage, StopReason, ToolCall, ToolResultMessage
from kwok.server.llm.provider.llm_provider import LlmProvider
from kwok.server.middleware import get_middleware_chain
from kwok.server.tools import get_tool_registry
from kwok.server.tools.runner import tool_execute

logger = logging.getLogger(__name__)

type MessageCallback = Callable[[AssistantMessage | ToolResultMessage], None]


async def run(
        provider: LlmProvider,
        prompt: str,
        turn_id: str,
        turns_dir: Path | None = None,
        on_message: MessageCallback | None = None,
        history: Sequence[dict[str, Any]] = (),
) -> None:
    bus = get_bus()
    config = get_config()
    messages: list[dict[str, Any]] = [*history, {"role": "user", "content": prompt}]

    context = LlmContext(
        turn_id=turn_id,
        prompt=prompt,
        bus=bus,
        max_steps=max(1, config.agent.max_steps),
        messages=messages,
        tools=get_tool_registry().schemas()
    )

    turnLogWriter = TurnLogWriterBus(turn_id=turn_id, base_dir=turns_dir)
    bus.subscribe(turnLogWriter.on_event)

    error: TurnErrorEvent | None = None
    try:
        await bus.publish(TurnStartEvent(turn_id=turn_id, prompt=prompt))
        try:
            await run_llm_loop(provider, context, on_message=on_message)
        except asyncio.CancelledError:
            raise
        except LlmError as exc:
            error = TurnErrorEvent(turn_id=turn_id, code=ErrorCode.LLM_ERROR, message=str(exc))
        except Exception as exc:
            logger.exception("chat 流式任务异常 turn_id=%s", turn_id)
            error = TurnErrorEvent(
                turn_id=turn_id, code=ErrorCode.INTERNAL_ERROR, message=f"handler error: {exc}"
            )

        if error is None and context.status == "failed":
            if context.reason == "max_steps":
                error = TurnErrorEvent(
                    turn_id=turn_id, code=ErrorCode.LLM_ERROR, message="已达步数上限，循环终止"
                )
            elif context.reason == "tool_not_configured":
                error = TurnErrorEvent(
                    turn_id=turn_id,
                    code=ErrorCode.LLM_ERROR,
                    message="模型请求调用工具，但未配置工具执行器",
                )
            else:
                logger.warning(
                    "loop 终止未达成功 status=%s reason=%s", context.status, context.reason
                )
        if error is not None:
            await bus.publish(error)
        if error is None and context.status == "success" and on_message is not None:
            on_message(AssistantMessage(content=context.text))
        await bus.publish(TurnFinishEvent(turn_id=turn_id, prompt=prompt))
    finally:
        bus.unsubscribe(turnLogWriter.on_event)
        turnLogWriter.close()


async def run_llm_loop(
        provider: LlmProvider,
        context: LlmContext,
        on_message: MessageCallback | None = None,
) -> str:
    while context.status == "running":
        if context.step >= context.max_steps:
            context.status, context.reason = "failed", "max_steps"
            break
        context.step += 1
        await context.bus.publish(StepStartEvent(turn_id=context.turn_id, step_id=context.step))
        resp = await get_middleware_chain().invoke_around_model(
            context, lambda: provider.stream_chat(context),
        )
        context.text += resp.text
        if resp.stop_reason is StopReason.FINISH:
            context.status, context.reason = "success", "stop"
            await context.bus.publish(
                StepFinishEvent(
                    turn_id=context.turn_id,
                    step_id=context.step,
                    finish_reason=context.reason,
                )
            )
            break
        if resp.stop_reason is StopReason.MAX_TOKENS:
            context.status, context.reason = "success", "max_tokens"
            await context.bus.publish(
                StepFinishEvent(
                    turn_id=context.turn_id,
                    step_id=context.step,
                    finish_reason=context.reason,
                )
            )
            break

        if not resp.tool_calls:
            context.status, context.reason = "success", "stop"
            await context.bus.publish(
                StepFinishEvent(
                    turn_id=context.turn_id,
                    step_id=context.step,
                    finish_reason=context.reason,
                )
            )
            break
        context.messages.append(
            {
                "role": "assistant",
                "content": resp.text or None,
                "tool_calls": [_as_tool_call_message(c) for c in resp.tool_calls],
            }
        )
        if on_message is not None:
            on_message(
                AssistantMessage(
                    content=resp.text,
                    tool_calls=[_as_tool_call_message(c) for c in resp.tool_calls],
                )
            )
        for call in resp.tool_calls:
            result = await tool_execute(call, context)
            context.messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
            if on_message is not None:
                on_message(ToolResultMessage(tool_call_id=call.id, name=call.name, content=result))
            await context.bus.publish(
                StepFinishEvent(
                    turn_id=context.turn_id,
                    step_id=context.step,
                    finish_reason="need tool call",
                )
            )

    return context.text


def _as_tool_call_message(call: ToolCall) -> dict[str, Any]:
    return {
        "id": call.id,
        "type": "function",
        "function": {"name": call.name, "arguments": call.arguments},
    }
