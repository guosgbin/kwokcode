from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

from pydantic import BaseModel

from kwok.server.llm.model import AssistantMessage, ToolResultMessage, UserMessage

MessageRole = Literal["user", "assistant", "tool"]


class TranscriptRecord(BaseModel):
    """会话消息记录，对应 <session-id>.jsonl 的每行。"""

    ts: str
    turn_id: str
    role: MessageRole
    content: str
    tool_call_id: str | None = None
    name: str | None = None
    tool_calls: list[dict[str, Any]] | None = None


def message_to_record(
        event: UserMessage | AssistantMessage | ToolResultMessage,
        *,
        turn_id: str,
        ts: str,
) -> TranscriptRecord:
    """把消息对象转成 transcript 落盘记录（isinstance 分派角色）。"""
    if isinstance(event, UserMessage):
        return TranscriptRecord(ts=ts, turn_id=turn_id, role="user", content=event.content)
    if isinstance(event, ToolResultMessage):
        return TranscriptRecord(
            ts=ts,
            turn_id=turn_id,
            role="tool",
            content=event.content,
            tool_call_id=event.tool_call_id,
            name=event.name,
        )
    return TranscriptRecord(
        ts=ts, turn_id=turn_id, role="assistant", content=event.content, tool_calls=event.tool_calls
    )


def records_to_messages(records: Sequence[TranscriptRecord]) -> list[dict[str, Any]]:
    """把 transcript 记录转换为 LLM wire 格式的 messages（保留工具调用结构，可无损回放）。"""
    messages: list[dict[str, Any]] = []
    for rec in records:
        if rec.role == "user":
            messages.append({"role": "user", "content": rec.content})
        elif rec.role == "assistant":
            content: str | None = None if (rec.tool_calls and not rec.content) else rec.content
            msg: dict[str, Any] = {"role": "assistant", "content": content}
            if rec.tool_calls:
                msg["tool_calls"] = rec.tool_calls
            messages.append(msg)
        else:
            messages.append(
                {"role": "tool", "tool_call_id": rec.tool_call_id or "", "content": rec.content}
            )
    return messages
