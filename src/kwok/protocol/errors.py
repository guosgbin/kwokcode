from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ErrorObject(BaseModel):
    code: int
    message: str
    data: Any | None = None


class RpcError(Exception):

    def __init__(self, code: int, message: str, data: Any | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


class RpcConnectionError(Exception):
    pass


class UnknownMethodError(Exception):
    pass


class InvalidParamsError(Exception):
    pass


class LlmError(Exception):
    pass
