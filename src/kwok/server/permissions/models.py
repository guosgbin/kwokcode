from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from kwok.protocol.enums import PermissionDecision
from kwok.server.permissions.errors import PermissionDeniedError, PermissionTimeoutError


class PermissionResult(StrEnum):
    """权限决策粗分类：granted / denied / timeout（runner/LLM 错误路由用）。"""

    GRANTED = "granted"
    DENIED = "denied"
    TIMEOUT = "timeout"


@dataclass(frozen=True)
class PermissionOutcome:
    """权限检查结果：分类 + 决策字符串 + 失败分类错误（两层级：Outcome 路由 / Decision 透传）。"""

    result: PermissionResult
    decision: PermissionDecision
    error: PermissionDeniedError | PermissionTimeoutError | None = None

    def to_tool_error_text(self) -> str:
        """转 LLM 可见文本：denied/timeout 用分类 token + 消息，其余用决策字符串。"""
        if self.error is not None:
            return f"{self.error.PREFIX}: {self.error.MESSAGE}"
        return self.decision.value


@dataclass(frozen=True)
class PermissionRequest:
    """permission.requested 事件载荷（含 param_preview / timeout_s）。"""

    tool_use_id: str
    session_id: str
    tool_name: str
    param_preview: str
    timeout_s: float | None = None
