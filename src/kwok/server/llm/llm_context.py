from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from kwok.server.event import EventBusManager


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
    text: str = ""
    tools: list[dict[str, object]] = field(default_factory=list)
    session_id: str = ""

