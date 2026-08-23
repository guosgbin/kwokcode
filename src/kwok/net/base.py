from __future__ import annotations

import asyncio
import json
from typing import Any

from pydantic import BaseModel, ValidationError

from kwok.protocol.rpc_model import MESSAGE_ADAPTER, Message


class NDJSONError(Exception):
    pass


class NDJSONDecodeError(NDJSONError):
    pass


def encode_line(message: BaseModel) -> str:
    return message.model_dump_json() + "\n"


def decode_line(line: str) -> Message:
    stripped = line.strip()
    if not stripped:
        raise NDJSONDecodeError("空行")
    try:
        data: Any = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise NDJSONDecodeError(f"非法 JSON: {exc}") from exc
    try:
        return MESSAGE_ADAPTER.validate_python(data)
    except ValidationError as exc:
        raise NDJSONDecodeError(f"非法 JSON-RPC 消息: {exc}") from exc


async def read_message(reader: asyncio.StreamReader) -> Message | None:
    line = await reader.readline()
    if not line:
        return None
    return decode_line(line.decode("utf-8"))


async def write_message(writer: asyncio.StreamWriter, message: Message) -> None:
    writer.write(encode_line(message).encode("utf-8"))
    await writer.drain()
