from __future__ import annotations

from kwok.protocol.events import (
    BaseEvent,
    ContextCompactedEvent,
    ContextCompactStartEvent,
    LLMChunkEvent,
    LLMReasoningChunkEvent,
    LLMUsageEvent,
    ServerStatusEvent,
    StepFinishEvent,
    StepStartEvent,
    ToolCallFinishEvent,
    ToolCallStartEvent,
    TurnErrorEvent,
    TurnFinishEvent,
    TurnStartEvent,
)
from kwok.tui.state import UiState
from kwok.tui.widgets.transcript import Transcript


class EventRenderer:
    """把 server 事件映射到 Transcript 更新与 UiState 变更（宪法 III：纯消费渲染）。"""

    def __init__(self, transcript: Transcript, state: UiState) -> None:
        self._transcript = transcript
        self._state = state

    async def handle(self, event: BaseEvent) -> None:
        if isinstance(event, TurnStartEvent):
            self._state.turn_in_flight = True
        elif isinstance(event, TurnFinishEvent):
            await self._transcript.close_reasoning()
            await self._transcript.finish_assistant()
            self._state.turn_in_flight = False
        elif isinstance(event, TurnErrorEvent):
            await self._transcript.close_reasoning()
            await self._transcript.finish_assistant()
            self._state.turn_in_flight = False
            self._transcript.add_error(f"turn {event.turn_id} 错误 [{event.code}]：{event.message}")
        elif isinstance(event, StepStartEvent):
            pass  # 步骤进度 v1 由 turn_in_flight 状态栏体现
        elif isinstance(event, StepFinishEvent):
            pass
        elif isinstance(event, LLMChunkEvent):
            # 正文首个 chunk 前关闭思考块（幂等：后续 chunk 为 no-op）
            await self._transcript.close_reasoning()
            await self._transcript.append_delta(event.delta)
        elif isinstance(event, LLMReasoningChunkEvent):
            await self._transcript.append_reasoning(event.delta)
        elif isinstance(event, LLMUsageEvent):
            self._state.tokens_in += event.input_tokens
            self._state.tokens_out += event.output_tokens
            self._state.tokens_cached += event.cached_tokens
            self._state.tokens_total += event.total_tokens
            self._state.context_pct = event.context_pct
        elif isinstance(event, ToolCallStartEvent):
            # 关闭当前思考块与流式块，让工具块插入思考与最终答案之间（对标 Claude Code）
            await self._transcript.close_reasoning()
            await self._transcript.finish_assistant()
            self._transcript.add_tool(event.tool_call_id, event.name, event.arguments)
        elif isinstance(event, ToolCallFinishEvent):
            self._transcript.update_tool(event.tool_call_id, event.result)
        elif isinstance(event, ContextCompactStartEvent):
            self._transcript.begin_compact(event.trigger)
        elif isinstance(event, ContextCompactedEvent):
            self._transcript.end_compact(
                f"⚡ 上下文已压缩：saved≈{event.saved_tokens} tokens，摘要 {event.summary_path}"
            )
        elif isinstance(event, ServerStatusEvent):
            # "running" 是服务端稳态，不应覆盖 TUI 的 connected（否则输入框被禁用）；
            # 仅 "stopping" 需要反映为停止中。
            if event.status == "stopping":
                self._state.connection_status = "stopping"
