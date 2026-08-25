from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
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


def _now_iso() -> str:
    """当前时间，ISO 8601 毫秒带时区。"""
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def messages_to_records(
    messages: Sequence[dict[str, Any]], *, turn_id: str = "", ts: str | None = None
) -> list[TranscriptRecord]:
    """把 LLM wire 格式的 messages 转回落盘记录（records_to_messages 的逆映射）。

    缺失 ts 用当前 ISO、缺失 turn_id 用入参补；assistant 的 tool_calls / tool 的
    tool_call_id 原样透传，保证 `records_to_messages(messages_to_records(msgs))`
    对消息内容无损回放。
    """
    stamp = ts if ts is not None else _now_iso()
    records: list[TranscriptRecord] = []
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content") or ""
        if role == "user":
            records.append(
                TranscriptRecord(ts=stamp, turn_id=turn_id, role="user", content=content)
            )
        elif role == "assistant":
            records.append(
                TranscriptRecord(
                    ts=stamp,
                    turn_id=turn_id,
                    role="assistant",
                    content=content,
                    tool_calls=msg.get("tool_calls"),
                )
            )
        else:
            records.append(
                TranscriptRecord(
                    ts=stamp,
                    turn_id=turn_id,
                    role="tool",
                    content=content,
                    tool_call_id=msg.get("tool_call_id"),
                )
            )
    return records
