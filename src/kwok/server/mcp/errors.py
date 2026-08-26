"""MCP 接入错误体系：连接层与调用层错误统一映射为工具结构化错误。

两个异常类均继承 ``ToolError``——runner（``_run_with_governance``）只对
``ToolError`` 走 ``_tool_error_text`` 结构化 JSON 通道，继承后 MCP 错误自动
以结构化文本返回模型（spec FR-016 runtime_error 语义），模型可换策略，不崩 daemon。
"""
from __future__ import annotations

from typing import Any

from kwok.server.tools.tool import ToolError


class McpServerUnavailableError(ToolError):
    """连接层错误：连接/握手失败、读超时、断连。"""

    def __init__(self, message: str, *, cause: BaseException | None = None) -> None:
        payload: dict[str, Any] = {"error": message, "type": "mcp_server_unavailable"}
        if cause is not None:
            payload["cause"] = str(cause)
        super().__init__(payload)


class McpToolError(ToolError):
    """工具调用应用层错误：server 返回 JSON-RPC error 或 is_error=True。"""

    def __init__(self, message: str, *, code: int | None = None) -> None:
        payload: dict[str, Any] = {"error": message, "type": "mcp_tool_error"}
        if code is not None:
            payload["code"] = code
        super().__init__(payload)
