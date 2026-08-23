from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from kwok.server.event.manager import EventBusManager
from kwok.server.llm.model import ToolCall


@dataclass
class LlmContext:
    turn_id: str
    prompt: str
    bus: EventBusManager
    max_steps: int = 20
    messages: list[dict[str, Any]] = field(default_factory=list)
    step: int = 0
    status: str = "running"
    reason: str | None = None
    tools: list[dict[str, object]] = field(default_factory=list)

    tool_executor: Callable[[ToolCall, LlmContext], Awaitable[str]] | None = None
    text: str = ""
