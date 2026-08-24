from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from kwok.server.event import EventBusManager
from kwok.server.tools.registry import get_tool_registry


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

    @property
    def tools(self) -> list[dict[str, object]]:
        """当前可执行工具的 OpenAI function schema 列表（锚定注册表单例，现算无快照）。"""
        return get_tool_registry().schemas()
