from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter, field_validator

from kwok.config import get_config

from .enums import Method
from .errors import ErrorObject
from .topics import validate_pattern

_PROMPT_MAX_LENGTH = get_config().llm.prompt_max_length

_JSONRPC_VERSION: Literal["2.0"] = "2.0"


class Request(BaseModel):
    jsonrpc: Literal["2.0"] = _JSONRPC_VERSION
    method: str
    params: dict[str, Any] | list[Any] | None = None
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


class PingJsonRpcReq(BaseModel):
    pass


class PingJsonRpcResp(BaseModel):
    type: Literal["pong"] = "pong"
    server_version: str
    uptime_ms: int
    received_at: str


class VersionJsonRpcReq(BaseModel):
    pass


class VersionJsonRpcResp(BaseModel):
    type: Literal["version"] = "version"
    version: str


class ChatJsonRpcReq(BaseModel):
    prompt: str

    @field_validator("prompt")
    @classmethod
    def _strip_and_check(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("提示词不能为空")
        if len(stripped) > _PROMPT_MAX_LENGTH:
            raise ValueError(f"提示词过长（>{_PROMPT_MAX_LENGTH} 字符）")
        return stripped


class ChatAcceptedJsonRpcResp(BaseModel):
    type: Literal["chat.accepted"] = "chat.accepted"
    turn_id: str


class SubscribeReq(BaseModel):
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


class UnsubscribeReq(BaseModel):
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


class EventTypesReq(BaseModel):
    pass


class EventTypesResp(BaseModel):
    type: Literal["event.types"] = "event.types"
    types: list[str]


REQ_BODY_CLASSES: dict[Method, type[BaseModel]] = {
    Method.PING: PingJsonRpcReq,
    Method.VERSION: VersionJsonRpcReq,
    Method.CHAT: ChatJsonRpcReq,
    Method.EVENT_SUBSCRIBE: SubscribeReq,
    Method.EVENT_UNSUBSCRIBE: UnsubscribeReq,
    Method.EVENT_TYPES: EventTypesReq,
}

RespUnion = (
        PingJsonRpcResp
        | VersionJsonRpcResp
        | ChatAcceptedJsonRpcResp
        | SubscribeResp
        | UnsubscribeResp
        | EventTypesResp
)
RESP_ADAPTER: TypeAdapter[RespUnion] = TypeAdapter(RespUnion)


def build_request(method: str, **kwargs: Any) -> BaseModel | None:
    try:
        name = Method(method)
    except ValueError:
        return None
    req_cls = REQ_BODY_CLASSES.get(name)
    return req_cls(**kwargs) if req_cls is not None else None
