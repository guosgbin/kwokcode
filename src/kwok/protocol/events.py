from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, TypeAdapter

from .enums import PermissionDecision


class EventType(StrEnum):
    TURN_START = "turn.start"
    TURN_FINISH = "turn.finish"
    TURN_ERROR = "turn.error"
    STEP_START = "step.start"
    STEP_FINISH = "step.finish"
    LLM_CHUNK = "llm.chunk"
    LLM_USAGE = "llm.usage"
    LLM_REASONING_CHUNK = "llm.reasoning_chunk"
    TOOL_CALL_START = "tool.call.start"
    TOOL_CALL_FINISH = "tool.call.finish"
    CHAT_DONE = "chat.done"
    SERVER_STATUS = "server.status"
    PERMISSION_REQUESTED = "permission.requested"
    PERMISSION_GRANTED = "permission.granted"
    PERMISSION_DENIED = "permission.denied"
    CONTEXT_COMPACT_START = "context.compact_start"
    CONTEXT_COMPACTED = "context.compacted"
    SUBAGENT_STARTED = "subagent.started"
    SUBAGENT_FINISHED = "subagent.finished"


class BaseEvent(BaseModel):
    type: EventType


class TurnStartEvent(BaseEvent):
    type: Literal[EventType.TURN_START] = EventType.TURN_START
    turn_id: str
    prompt: str


class TurnFinishEvent(BaseEvent):
    type: Literal[EventType.TURN_FINISH] = EventType.TURN_FINISH
    turn_id: str
    prompt: str


class TurnErrorEvent(BaseEvent):
    type: Literal[EventType.TURN_ERROR] = EventType.TURN_ERROR
    turn_id: str
    code: int
    message: str


class StepStartEvent(BaseEvent):
    type: Literal[EventType.STEP_START] = EventType.STEP_START
    turn_id: str
    step_id: int


class StepFinishEvent(BaseEvent):
    type: Literal[EventType.STEP_FINISH] = EventType.STEP_FINISH
    turn_id: str
    step_id: int
    finish_reason: str


class ToolCallStartEvent(BaseEvent):
    type: Literal[EventType.TOOL_CALL_START] = EventType.TOOL_CALL_START
    turn_id: str
    step_id: int
    tool_call_id: str
    name: str
    arguments: str = ""


class ToolCallFinishEvent(BaseEvent):
    type: Literal[EventType.TOOL_CALL_FINISH] = EventType.TOOL_CALL_FINISH
    turn_id: str
    step_id: int
    tool_call_id: str
    name: str
    result: str


class LLMChunkEvent(BaseEvent):
    type: Literal[EventType.LLM_CHUNK] = EventType.LLM_CHUNK
    turn_id: str
    delta: str


class LLMReasoningChunkEvent(BaseEvent):
    """模型思考增量（reasoning / thinking）：不落盘、不回传模型，仅内存展示。"""

    type: Literal[EventType.LLM_REASONING_CHUNK] = EventType.LLM_REASONING_CHUNK
    turn_id: str
    delta: str


class LLMUsageEvent(BaseEvent):
    type: Literal[EventType.LLM_USAGE] = EventType.LLM_USAGE
    turn_id: str
    step_id: int
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    total_tokens: int
    context_pct: float = 0.0


class TurnStartHandlerChatDoneEvent(BaseEvent):
    type: Literal[EventType.CHAT_DONE] = EventType.CHAT_DONE
    turn_id: str
    full_text: str


class ServerStatusEvent(BaseEvent):
    type: Literal[EventType.SERVER_STATUS] = EventType.SERVER_STATUS
    status: Literal["running", "stopping"]
    server_version: str
    uptime_ms: int
    received_at: str


class PermissionRequestedEvent(BaseEvent):
    type: Literal[EventType.PERMISSION_REQUESTED] = EventType.PERMISSION_REQUESTED
    tool_use_id: str
    session_id: str
    tool_name: str
    param_preview: str
    timeout_s: float | None = None


class PermissionGrantedEvent(BaseEvent):
    type: Literal[EventType.PERMISSION_GRANTED] = EventType.PERMISSION_GRANTED
    tool_use_id: str
    session_id: str
    tool_name: str
    decision: PermissionDecision


class PermissionDeniedEvent(BaseEvent):
    type: Literal[EventType.PERMISSION_DENIED] = EventType.PERMISSION_DENIED
    tool_use_id: str
    session_id: str
    tool_name: str
    decision: PermissionDecision


class ContextCompactStartEvent(BaseEvent):
    type: Literal[EventType.CONTEXT_COMPACT_START] = EventType.CONTEXT_COMPACT_START
    session_id: str
    trigger: Literal["manual", "auto"]


class ContextCompactedEvent(BaseEvent):
    type: Literal[EventType.CONTEXT_COMPACTED] = EventType.CONTEXT_COMPACTED
    session_id: str
    summary_path: str
    saved_tokens: int
    kept_recent_turns: int


class SubagentStartedEvent(BaseEvent):
    type: Literal[EventType.SUBAGENT_STARTED] = EventType.SUBAGENT_STARTED
    child_turn_id: str
    parent_turn_id: str
    description: str


class SubagentFinishedEvent(BaseEvent):
    type: Literal[EventType.SUBAGENT_FINISHED] = EventType.SUBAGENT_FINISHED
    child_turn_id: str
    parent_turn_id: str
    status: Literal["success", "failed", "cancelled"]


Event = (LLMChunkEvent
         | LLMReasoningChunkEvent
         | LLMUsageEvent
         | TurnErrorEvent
         | ServerStatusEvent
         | TurnStartEvent
         | TurnFinishEvent
         | StepStartEvent
         | StepFinishEvent
         | ToolCallStartEvent
         | ToolCallFinishEvent
         | PermissionRequestedEvent
         | PermissionGrantedEvent
         | PermissionDeniedEvent
         | ContextCompactStartEvent
         | ContextCompactedEvent
         | SubagentStartedEvent
         | SubagentFinishedEvent
         )
EVENT_ADAPTER: TypeAdapter[Event] = TypeAdapter(Event)
