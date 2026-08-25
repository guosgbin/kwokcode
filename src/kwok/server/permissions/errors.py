from __future__ import annotations


class PermissionDeniedError(Exception):
    """失败分类：工具调用被用户拒绝（与 ToolError 区分，SC-007）。

    PREFIX 是 wire 级分类 token；MESSAGE 是 LLM 可见消息文本来源。
    """

    PREFIX = "permission_denied"
    MESSAGE = "工具调用被用户拒绝"


class PermissionTimeoutError(Exception):
    """失败分类：审批超时未获批准（与 ToolError 区分，SC-007）。"""

    PREFIX = "permission_timeout"
    MESSAGE = "审批超时未获批准"


class PermissionBlacklistError(Exception):
    """失败分类：命令被系统高危黑名单强制拒绝（与用户拒绝区分）。

    PREFIX 为 wire 级分类 token；MESSAGE 由 reason 具体化，指出被拦原因。
    """

    PREFIX = "permission_blacklisted"
    MESSAGE = "该命令被系统列为高危操作，已强制拒绝"

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"{self.PREFIX}: {reason}")
