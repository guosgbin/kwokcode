from __future__ import annotations

import asyncio
import json
import time
from typing import TYPE_CHECKING, Any

from kwok.server.llm.model import ToolCall
from kwok.server.middleware import get_middleware_chain
from kwok.server.tools.tool import RetryStrategy, Tool, ToolError

if TYPE_CHECKING:
    from kwok.server.llm.llm_context import LlmContext


async def tool_execute(call: ToolCall, ctx: LlmContext) -> str:
    async def _core() -> str:
        tool = call.resolved_tool
        args = call.validated_args
        # 参数校验中间件（ToolParamCheckMiddleware）保证执行前已填充这两个字段
        assert tool is not None, "工具未解析（resolved_tool 缺失）"
        assert args is not None, "工具参数未校验（validated_args 缺失）"
        result = await _run_with_governance(tool, args)
        if isinstance(result, str):
            return result
        if tool.output_model is not None:
            try:
                tool.output_model.model_validate(result)
            except Exception as exc:
                return f"工具输出不符合声明结构：{exc}"
        return json.dumps(result, ensure_ascii=False)

    return await get_middleware_chain().invoke_around_tool(ctx, call, _core)


async def _run_with_governance(
    tool: Tool, args: dict[str, Any]
) -> dict[str, Any] | str:
    """执行 + 错误通道：单次 timeout + all_timeout 总预算 + RetryStrategy 指数退避。"""
    deadline = (
        time.monotonic() + tool.all_timeout if tool.all_timeout is not None else None
    )
    retry_policy = tool.retry_policy
    attempt = 0
    while True:
        if deadline is not None and time.monotonic() >= deadline:
            return "工具整体执行超时（all_timeout 已到达）"
        remaining = deadline - time.monotonic() if deadline is not None else None
        per_timeout = tool.timeout
        if remaining is not None:
            per_timeout = (
                remaining if per_timeout is None else min(per_timeout, remaining)
            )
        try:
            return await _run_once(tool, args, per_timeout)
        except ToolError as exc:
            if not _can_retry(retry_policy, exc, attempt):
                return _tool_error_text(tool, exc)
        except TimeoutError:
            if not _can_retry(retry_policy, TimeoutError(), attempt):
                return "工具执行超时"
        except Exception as exc:
            if not _can_retry(retry_policy, exc, attempt):
                return f"工具执行失败：{exc}"
        # 到达此处说明需要重试：退避后进入下一轮（deadline 在循环顶部再校验）
        await _backoff(retry_policy, attempt, deadline)
        attempt += 1


async def _run_once(
    tool: Tool, args: dict[str, Any], timeout: float | None
) -> dict[str, Any]:
    """单次执行；timeout <= 0 视为未配置不包裹。"""
    if timeout is not None and timeout > 0:
        return await asyncio.wait_for(asyncio.to_thread(tool.execute, args), timeout)
    return await asyncio.to_thread(tool.execute, args)


def _can_retry(
    policy: RetryStrategy | None, error: Exception, attempt: int
) -> bool:
    """是否重试：配置了策略、未超追加重试上限、且异常可重试。"""
    return policy is not None and attempt < policy.max_retries and policy.is_retryable(
        error
    )


async def _backoff(
    policy: RetryStrategy | None, attempt: int, deadline: float | None
) -> None:
    """指数退避 sleep；退避会超预算则直接不睡（循环顶部统一判整体超时）。"""
    if policy is None:
        return
    delay = policy.backoff_seconds * (policy.backoff_multiplier**attempt)
    if deadline is not None:
        remaining = deadline - time.monotonic()
        if remaining <= 0 or delay >= remaining:
            return
        delay = min(delay, remaining)
    await asyncio.sleep(delay)


def _tool_error_text(tool: Tool, exc: ToolError) -> str:
    """ToolError 错误通道：声明 error_model 则校验 payload，否则序列化 payload。"""
    if tool.error_model is not None:
        try:
            tool.error_model.model_validate(exc.payload)
        except Exception as validation_error:
            return f"工具错误校验失败：{validation_error}"
    return json.dumps(exc.payload, ensure_ascii=False)
