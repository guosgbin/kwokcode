from __future__ import annotations

from enum import IntEnum, StrEnum


class ErrorCode(IntEnum):
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    INVALID_PARAMS = -32602
    METHOD_NOT_FOUND = -32601
    INTERNAL_ERROR = -32603
    LLM_ERROR = -32000


class Method(StrEnum):
    PING = "ping"
    VERSION = "version"
    CHAT = "chat"
    EVENT_SUBSCRIBE = "event.subscribe"
    EVENT_UNSUBSCRIBE = "event.unsubscribe"
    EVENT_TYPES = "event.types"
