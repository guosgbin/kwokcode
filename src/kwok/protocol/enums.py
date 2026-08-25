from __future__ import annotations

from enum import IntEnum, StrEnum


class PermissionDecision(StrEnum):
    """权限决策字符串，全链路透传（协议传输 / 事件 / 缓存 / TUI 快捷键）。"""

    ALLOW_ONCE = "allow_once"
    SESSION_ALLOW = "session_allow"
    DENY_ONCE = "deny_once"
    SESSION_DENY = "session_deny"
    AUTO_ALLOW = "auto_allow"
    AUTO_DENY = "auto_deny"
    TIMEOUT = "timeout"


# 允许经 permission.respond 命令回传的交互决策白名单；auto_*/timeout 仅由服务端内部产生
INTERACTIVE_DECISIONS = (
    PermissionDecision.ALLOW_ONCE,
    PermissionDecision.SESSION_ALLOW,
    PermissionDecision.DENY_ONCE,
    PermissionDecision.SESSION_DENY,
)


class ErrorCode(IntEnum):
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    INVALID_PARAMS = -32602
    METHOD_NOT_FOUND = -32601
    INTERNAL_ERROR = -32603
    LLM_ERROR = -32000
    PERMISSION_DENIED = -32001  # 预留：权限被拒的 RPC 级分类
    PERMISSION_TIMEOUT = -32002  # 预留：审批超时的 RPC 级分类
