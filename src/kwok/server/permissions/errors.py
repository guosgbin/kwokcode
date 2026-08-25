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
