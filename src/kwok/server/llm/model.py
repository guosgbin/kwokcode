from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class StopReason(StrEnum):
    FINISH = "finish"
    TOOL_USE = "tool_use"
    MAX_TOKENS = "max_tokens"


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass
class LlmResponse:
    stop_reason: StopReason
    tool_calls: list[ToolCall] = field(default_factory=list)
    text: str = ""
