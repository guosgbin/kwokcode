from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kwok.server.tools.tool import Tool


class StopReason(StrEnum):
    FINISH = "finish"
    TOOL_USE = "tool_use"
    MAX_TOKENS = "max_tokens"


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str

    # 运行时字段，由 tool_execute 在中间件链路中填充
    resolved_tool: Tool | None = None
    validated_args: dict[str, Any] | None = None


@dataclass
class LlmResponse:
    stop_reason: StopReason
    tool_calls: list[ToolCall] = field(default_factory=list)
    text: str = ""


@dataclass(frozen=True)
class UserMessage:
    """会话输入：一轮 turn 的用户 prompt。"""

    content: str


@dataclass(frozen=True)
class AssistantMessage:
    """LLM 产出：完整文本 +（可选）工具调用结构。"""

    content: str
    tool_calls: list[dict[str, Any]] | None = None


@dataclass(frozen=True)
class ToolResultMessage:
    """工具执行结果。"""

    tool_call_id: str
    name: str
    content: str
