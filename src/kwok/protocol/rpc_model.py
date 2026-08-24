from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter, field_validator

from kwok.config import get_config

from .errors import ErrorObject
from .topics import validate_pattern

_PROMPT_MAX_LENGTH = get_config().llm.prompt_max_length

_JSONRPC_VERSION: Literal["2.0"] = "2.0"


class Method(StrEnum):
    PING = "ping"
    VERSION = "version"
    PROMPT = "prompt"
    EVENT_SUBSCRIBE = "event.subscribe"
    EVENT_UNSUBSCRIBE = "event.unsubscribe"
    SESSION_CREATE = "session.create"
    SESSION_CLOSE = "session.close"


class Request(BaseModel):
    jsonrpc: Literal["2.0"] = _JSONRPC_VERSION
    method: str
    params: Any = None
    id: int | str | None = None


class Response(BaseModel):
    jsonrpc: Literal["2.0"] = _JSONRPC_VERSION
    result: Any
    id: int | str


class ErrorResponse(BaseModel):
    jsonrpc: Literal["2.0"] = _JSONRPC_VERSION
    error: ErrorObject
    id: int | str | None = None


class RpcFrame(BaseModel):
    type: Literal["rpc"] = "rpc"
    rpc: Request | Response | ErrorResponse


class EventFrame(BaseModel):
    type: Literal["event"] = "event"
    event: str
    params: dict[str, Any] | None = None


Message = Annotated[RpcFrame | EventFrame, Field(discriminator="type")]

MESSAGE_ADAPTER: TypeAdapter[Message] = TypeAdapter(Message)


def make_error(
        code: int,
        message: str,
        data: Any | None = None,
        *,
        id: int | str | None = None,
) -> ErrorResponse:
    return ErrorResponse(error=ErrorObject(code=code, message=message, data=data), id=id)


class BaseRpcReq(BaseModel):
    method: Method


class PingJsonRpcReq(BaseRpcReq):
    method: Method = Method.PING


class PingJsonRpcResp(BaseModel):
    type: Literal["pong"] = "pong"
    server_version: str
    uptime_ms: int
    received_at: str


class VersionJsonRpcReq(BaseRpcReq):
    method: Method = Method.VERSION


class VersionJsonRpcResp(BaseModel):
    type: Literal["version"] = "version"
    version: str


class PromptReq(BaseRpcReq):
    method: Method = Method.PROMPT
    prompt: str
    session_id: str | None = None
    cwd: str | None = None

    @field_validator("prompt")
    @classmethod
    def _strip_and_check(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("提示词不能为空")
        if len(stripped) > _PROMPT_MAX_LENGTH:
            raise ValueError(f"提示词过长（>{_PROMPT_MAX_LENGTH} 字符）")
        return stripped


class PromptResp(BaseModel):
    type: Literal["prompt"] = "prompt"
    turn_id: str


class SubscribeReq(BaseRpcReq):
    method: Method = Method.EVENT_SUBSCRIBE
    patterns: list[str]

    @field_validator("patterns")
    @classmethod
    def _validate_patterns(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("订阅模式列表不能为空")
        for pattern in value:
            validate_pattern(pattern)
        return value


class SubscribeResp(BaseModel):
    type: Literal["subscribe"] = "subscribe"
    connection_id: str
    patterns: list[str]


class UnsubscribeReq(BaseRpcReq):
    method: Method = Method.EVENT_UNSUBSCRIBE
    patterns: list[str]

    @field_validator("patterns")
    @classmethod
    def _validate_patterns(cls, value: list[str]) -> list[str]:
        for pattern in value:
            validate_pattern(pattern)
        return value


class UnsubscribeResp(BaseModel):
    type: Literal["unsubscribe"] = "unsubscribe"
    patterns: list[str]


class SessionCreateReq(BaseRpcReq):
    method: Method = Method.SESSION_CREATE
    cwd: str
    name: str | None = None


class SessionCreateResp(BaseModel):
    type: Literal["session.create"] = "session.create"
    session_id: str
    name: str


class SessionCloseReq(BaseRpcReq):
    method: Method = Method.SESSION_CLOSE
    session_id: str


class SessionCloseResp(BaseModel):
    type: Literal["session.close"] = "session.close"
    session_id: str
