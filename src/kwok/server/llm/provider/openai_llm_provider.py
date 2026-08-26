from __future__ import annotations

import json
import logging
from typing import Any, cast

from openai import (
    APIConnectionError,
    APIError,
    AsyncOpenAI,
    AuthenticationError,
    ContentFilterFinishReasonError,
    LengthFinishReasonError,
    PermissionDeniedError,
    RateLimitError,
)

from kwok.config import KwokConfig
from kwok.protocol.errors import LlmError
from kwok.protocol.events import LLMChunkEvent, LLMReasoningChunkEvent, LLMUsageEvent
from kwok.server.llm.llm_context import LlmContext
from kwok.server.llm.model import LlmResponse, StopReason, ToolCall
from kwok.server.llm.provider.llm_provider import LlmProvider

__all__ = ["LlmProvider", "OpenAIProvider", "build_provider"]

logger = logging.getLogger(__name__)


class OpenAIProvider(LlmProvider):

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str | None = None,
        max_tokens: int = 8192,
        context_window: int = 128000,
        reasoning_effort: str | None = None,
    ) -> None:
        # 默认值镜像 config.py 的 _DEFAULT_MAX_TOKENS / _DEFAULT_CONTEXT_WINDOW；
        # build_provider 始终注入真实配置值。
        self._model = model
        self._max_tokens = max_tokens
        self._context_window = context_window
        self._reasoning_effort = reasoning_effort
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def stream_chat(self, context: LlmContext) -> LlmResponse:

        usage: Any = None
        reasoning_parts: list[str] = []
        stream_kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": cast(Any, _messages(context)),
            "stream_options": {"include_usage": True},
            "max_tokens": self._max_tokens,
        }
        if self._reasoning_effort is not None:
            stream_kwargs["reasoning_effort"] = self._reasoning_effort
        if context.tools:
            stream_kwargs["tools"] = cast(Any, context.tools)
        try:
            async with self._client.chat.completions.stream(**stream_kwargs) as stream:
                async for event in stream:
                    if event.type == "chunk":
                        if event.chunk.usage is not None:
                            usage = event.chunk.usage
                        for piece in _reasoning_deltas(event.chunk):
                            await context.bus.publish(
                                LLMReasoningChunkEvent(turn_id=context.turn_id, delta=piece)
                            )
                            reasoning_parts.append(piece)
                    elif event.type == "content.delta":
                        await context.bus.publish(
                            LLMChunkEvent(turn_id=context.turn_id, delta=event.delta)
                        )
                completion: Any
                try:
                    completion = await stream.get_final_completion()
                except LengthFinishReasonError as exc:

                    completion = exc.completion
                except ContentFilterFinishReasonError as exc:
                    raise LlmError("内容被安全策略拦截（content_filter）") from exc
        except (AuthenticationError, PermissionDeniedError) as exc:
            raise LlmError(f"OpenAI 鉴权失败：{exc}") from exc
        except RateLimitError as exc:
            raise LlmError(f"OpenAI 限流：{exc}") from exc
        except APIConnectionError as exc:
            raise LlmError(f"无法连接 OpenAI：{exc}") from exc
        except APIError as exc:
            raise LlmError(f"OpenAI 调用失败：{exc}") from exc
        except json.JSONDecodeError as exc:

            raise LlmError(f"工具参数解析失败：{exc}") from exc

        if usage is not None:
            details = usage.prompt_tokens_details
            window = self._context_window or 1
            context.context_pct = min(usage.prompt_tokens / window, 1.0)
            await context.bus.publish(
                LLMUsageEvent(
                    turn_id=context.turn_id,
                    step_id=context.step,
                    input_tokens=usage.prompt_tokens,
                    output_tokens=usage.completion_tokens,
                    cached_tokens=details.cached_tokens if details is not None else 0,
                    total_tokens=usage.total_tokens,
                    context_pct=context.context_pct,
                )
            )

        message = completion.choices[0].message
        return LlmResponse(
            stop_reason=_normalize_stop_reason(completion.choices[0].finish_reason),
            tool_calls=[
                ToolCall(id=t.id, name=t.function.name, arguments=t.function.arguments)
                for t in (message.tool_calls or [])
            ],
            text=message.content or "",
            reasoning="".join(reasoning_parts),
        )


def _messages(context: LlmContext) -> list[dict[str, Any]]:
    """构造发给 API 的 messages：system_prompt 前置 + L1 截断视图（read_messages）。

    逐条重建副本并剥除 `reasoning` 键（FR-006，DeepSeek 兼容硬约束）：TranscriptRecord
    无该字段、读回未知键被 pydantic 忽略 → records_to_messages 天然无 reasoning；此处
    兜底任何上游误注入。重建而非原地 pop——read_messages 对非 tool 消息返回的是
    self.messages 的同一 dict 引用，原地改动会污染内存态。
    """
    system = context.system_prompt()
    body = [{k: v for k, v in msg.items() if k != "reasoning"} for msg in context.read_messages()]
    if not system:
        return body
    return [{"role": "system", "content": system}, *body]


def _reasoning_deltas(chunk: Any) -> list[str]:
    """从流式 chunk 提取思考增量（两种供应商风格，空增量忽略）。

    openai v3 的 ChoiceDelta 为 extra='allow'，思考字段落在 model_extra 中：
    `reasoning_content`（DeepSeek 字符串增量）与 `reasoning`（o 系列块数组）都收。
    无思考 chunk 返回空列表 → 零事件（向后兼容，FR-005）。
    """
    if not chunk.choices:
        return []
    extra = chunk.choices[0].delta.model_extra or {}
    pieces: list[str] = []
    content = extra.get("reasoning_content")
    if isinstance(content, str) and content:
        pieces.append(content)
    items = extra.get("reasoning")
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str) and text:
                    pieces.append(text)
    return pieces


def _normalize_stop_reason(raw: str | None) -> StopReason:
    if raw is None:
        return StopReason.FINISH
    if raw == "stop":
        return StopReason.FINISH
    if raw == "tool_calls":
        return StopReason.TOOL_USE
    if raw == "length":
        return StopReason.MAX_TOKENS
    if raw == "content_filter":
        raise LlmError("内容被安全策略拦截（content_filter）")
    logger.warning("未知 finish_reason=%s，按 finish 处理", raw)
    return StopReason.FINISH


def build_provider(config: KwokConfig) -> LlmProvider | None:
    api_key = config.llm.api_key
    model = config.llm.model
    if not api_key or not model:
        raise LlmError("模型未配置，请检查 api_key 和 model 是否配置正确")
    base_url = config.llm.base_url
    return OpenAIProvider(
        model=model,
        api_key=api_key,
        base_url=base_url,
        max_tokens=config.llm.max_tokens,
        context_window=config.compaction.context_window,
        reasoning_effort=config.llm.reasoning_effort,
    )
