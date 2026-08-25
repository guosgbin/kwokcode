from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from kwok.config import get_config
from kwok.protocol.enums import ErrorCode
from kwok.protocol.errors import LlmError
from kwok.protocol.events import (
    ContextCompactedEvent,
    ContextCompactStartEvent,
    StepFinishEvent,
    StepStartEvent,
    TurnErrorEvent,
    TurnFinishEvent,
    TurnStartEvent,
)
from kwok.server.compact import Compactor, CompactResult
from kwok.server.event import get_bus
from kwok.server.event.turn_log_writer_bus import TurnLogWriterBus
from kwok.server.llm.llm_context import LlmContext
from kwok.server.llm.model import AssistantMessage, StopReason, ToolCall, ToolResultMessage
from kwok.server.llm.provider.llm_provider import LlmProvider
from kwok.server.memory import load_global_and_project
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
        session_id: str = "",
        project_memory_idx: str = "",
        on_compact: Callable[[CompactResult], None] | None = None,
        skill_prompt: str = "",
        allowed_tools: list[str] | None = None,
) -> None:
    bus = get_bus()
    config = get_config()
    messages: list[dict[str, Any]] = [*history, {"role": "user", "content": prompt}]

    global_ctx, project_ctx = load_global_and_project()

    context = LlmContext(
        turn_id=turn_id,
        prompt=prompt,
        bus=bus,
        max_steps=max(1, config.agent.max_steps),
        messages=messages,
        tools=get_tool_registry().allowed_tool_schemas(allowed_tools),
        session_id=session_id,
        project_memory_idx=project_memory_idx,
        global_ctx=global_ctx,
        project_ctx=project_ctx,
        skill_prompt=skill_prompt,
        session_dir=str(turns_dir.parent) if turns_dir else "",
    )

    turnLogWriter = TurnLogWriterBus(turn_id=turn_id, base_dir=turns_dir)
    bus.subscribe(turnLogWriter.on_event)

    error: TurnErrorEvent | None = None
    try:
        await bus.publish(TurnStartEvent(turn_id=turn_id, prompt=prompt))
        try:
            await run_llm_loop(provider, context, on_message=on_message, on_compact=on_compact)
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
        on_compact: Callable[[CompactResult], None] | None = None,
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
            if resp.tool_calls:
                # 输出被 max_tokens 截断产生不完整 tool_call：追加 assistant(tool_calls)，并为
                # 每个孤儿 tool_use 合成错误 tool 结果，维持配对平衡（否则下一轮 OpenAI 400）。
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
                    err = "<error: 输出被 max_tokens 截断，工具参数不完整>"
                    context.messages.append(
                        {"role": "tool", "tool_call_id": call.id, "content": err}
                    )
                    if on_message is not None:
                        on_message(
                            ToolResultMessage(tool_call_id=call.id, name=call.name, content=err)
                        )
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
        await maybe_auto_compact(provider, context, on_compact)

    return context.text


async def maybe_auto_compact(
        provider: LlmProvider,
        context: LlmContext,
        on_compact: Callable[[CompactResult], None] | None,
) -> None:
    """工具执行后按阈值触发自动压缩；失败静默跳过（messages 与 jsonl 均不变）。

    前置跳过：`auto_threshold <= 0.0`（默认禁用）、`context_pct < 阈值`、或 user 消息
    ≤ keep_recent（无可压缩的更早历史）时不触发。压缩调用走静默总线（compactor 内部
    临时 bus），usage 不污染主事件流；成功后替换 `context.messages`、发布
    ContextCompactedEvent、经 on_compact(result) 写回 jsonl（跨 turn 持久，
    result.ts 供 transcript 备份命名）。
    """
    config = get_config()
    threshold = config.compaction.auto_threshold
    if threshold <= 0.0 or context.context_pct < threshold:
        return
    user_count = sum(1 for m in context.messages if m.get("role") == "user")
    if user_count <= config.compaction.keep_recent:
        return
    session_dir = Path(context.session_dir) if context.session_dir else Path(".")
    compactor = Compactor()
    await context.bus.publish(
        ContextCompactStartEvent(session_id=context.session_id, trigger="auto")
    )
    try:
        result = await compactor.compact_messages(
            provider,
            context.messages,
            keep_recent=config.compaction.keep_recent,
            session_dir=session_dir,
            turn_id=context.turn_id,
        )
    except Exception:
        logger.exception("自动压缩失败，静默跳过 turn_id=%s", context.turn_id)
        return
    context.messages = result.compacted_messages
    await context.bus.publish(
        ContextCompactedEvent(
            session_id=context.session_id,
            summary_path=str(result.summary_path),
            saved_tokens=result.saved_tokens,
            kept_recent_turns=config.compaction.keep_recent,
        )
    )
    if on_compact is not None:
        on_compact(result)


def _as_tool_call_message(call: ToolCall) -> dict[str, Any]:
    return {
        "id": call.id,
        "type": "function",
        "function": {"name": call.name, "arguments": call.arguments},
    }
