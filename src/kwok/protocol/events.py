from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, TypeAdapter


class EventType(StrEnum):
    TURN_START = "turn.start"
    TURN_FINISH = "turn.finish"
    TURN_ERROR = "turn.error"
    STEP_START = "step.start"
    STEP_FINISH = "step.finish"
    LLM_CHUNK = "llm.chunk"
    LLM_USAGE = "llm.usage"
    TOOL_CALL_START = "tool.call.start"
    TOOL_CALL_FINISH = "tool.call.finish"
    CHAT_DONE = "chat.done"
    SERVER_STATUS = "server.status"


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


class LLMUsageEvent(BaseEvent):
    type: Literal[EventType.LLM_USAGE] = EventType.LLM_USAGE
    turn_id: str
    step_id: int
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    total_tokens: int


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


Event = (LLMChunkEvent
         | LLMUsageEvent
         | TurnErrorEvent
         | ServerStatusEvent
         | TurnStartEvent
         | TurnFinishEvent
         | StepStartEvent
         | StepFinishEvent
         | ToolCallStartEvent
         | ToolCallFinishEvent
         )
EVENT_ADAPTER: TypeAdapter[Event] = TypeAdapter(Event)
