from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from kwok.server.event import EventBusManager

if TYPE_CHECKING:
    from kwok.server.tools.runner import ToolRunner


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

    text: str = ""

    tool_runner: ToolRunner | None = None
