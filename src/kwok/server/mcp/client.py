"""协议层：基于官方 mcp python-sdk 的统一 ClientSession 封装。

McpClient 负责四件事（plan D4，FR-008/FR-009）：连接参数构造（stdio /
Streamable HTTP 双传输）、握手（``session.initialize()``，SDK 完成
initialized 通知与协议版本协商，FR-013）、工具发现与调用、异常统一分级映射。
分帧 / 请求-响应按 id 匹配 / 通知忽略 / 读超时由 SDK 承担（FR-010/FR-012）；
SDK 把超时与断连归一为 ``MCPError(code=REQUEST_TIMEOUT / CONNECTION_CLOSED)``，
McpClient 据此映射 ``McpServerUnavailableError``（FR-011），其余协议错误映射
``McpToolError``（FR-016）。调用结果为 ``content`` 中全部 ``TextContent.text``
拼接（FR-015）。
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from typing import Any, NoReturn

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import MCPError
from mcp.types import CallToolResult, TextContent
from pydantic import ValidationError

from kwok.config import McpServerConfig
from kwok.server.mcp.errors import McpServerUnavailableError, McpToolError

logger = logging.getLogger(__name__)

# SDK 归一化的连接层错误码（shared/jsonrpc_dispatcher）：连接关闭 / 读超时
_MCP_CONNECTION_CLOSED = -32000
_MCP_REQUEST_TIMEOUT = -32001

ToolDef = dict[str, Any]  # {name, description, input_schema}


class McpClient:
    """单个 MCP server 的 SDK 会话封装（stdio/http 双传输，FR-008/FR-009）。"""

    def __init__(self, cfg: McpServerConfig, read_timeout: float = 30.0) -> None:
        self._cfg = cfg
        self._read_timeout = read_timeout
        self._session: ClientSession | None = None
        self._transport: Any | None = None

    async def connect(self) -> None:
        """建立传输 + 会话 + initialize 握手；失败映射 McpServerUnavailableError。

        幂等：已连接则直接返回。失败时尽量释放半开资源（transport/session）。
        """
        if self._session is not None:
            return
        transport = self._build_transport()
        self._transport = transport  # close() 兜底用（可能半开）
        session: ClientSession | None = None
        try:
            read_stream, write_stream = await transport.__aenter__()
            session = ClientSession(
                read_stream, write_stream, read_timeout_seconds=self._read_timeout
            )
            await session.__aenter__()
            await session.initialize()
        except BaseException as exc:
            if session is not None:
                await _safe_exit(session, f"MCP session {self._cfg.name}")
            await self.close()
            if isinstance(exc, asyncio.CancelledError):
                raise
            raise McpServerUnavailableError(
                f"连接 MCP server {self._cfg.name!r} 失败", cause=exc
            ) from exc
        self._session = session

    def _build_transport(self) -> Any:
        """按 transport 类型构造传输上下文管理器（stdio 子进程 / Streamable HTTP）。"""
        if self._cfg.transport == "stdio":
            params = StdioServerParameters(
                command=self._cfg.command or "",
                args=self._cfg.args,
                env=self._cfg.env,
                cwd=self._cfg.cwd,
            )
            return stdio_client(params)
        return streamable_http_client(self._cfg.url or "")

    async def list_tools(self) -> list[ToolDef]:
        """发现工具 schema（SDK 完成 initialize→initialized→tools/list，FR-004/FR-013）。"""
        session = self._require_session()
        try:
            result = await session.list_tools()
        except MCPError as exc:
            self._map_sdk_error(exc, "工具发现")
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for tool in result.tools
        ]

    async def call_tool(self, name: str, args: dict[str, Any] | None = None) -> str:
        """调用工具并拼接 text 返回（FR-015）；SDK 异常分级映射（FR-011/FR-016）。"""
        session = self._require_session()
        try:
            result = await session.call_tool(name, arguments=args)
        except MCPError as exc:
            self._map_sdk_error(exc, f"调用 {name!r}")
        except (TimeoutError, ConnectionError, EOFError) as exc:
            raise McpServerUnavailableError(
                f"MCP server {self._cfg.name!r} 连接中断：{exc}", cause=exc
            ) from exc
        except ValidationError as exc:
            # 协议 surface 校验失败（如 server 的 structuredContent 非对象，见 mcp-go 兼容问题）：
            # 结构化错误返回，不让 daemon 崩/挂（FR-016 fail-closed）。
            raise McpToolError(
                f"MCP server {self._cfg.name!r} 调用 {name!r} 返回不符合协议 schema 的结果"
                f"（通常为 structuredContent 应为对象）：{exc}"
            ) from exc
        if not isinstance(result, CallToolResult):
            raise McpToolError(f"MCP server {self._cfg.name!r} 调用 {name!r} 未返回工具结果")
        text = _extract_text(result.content)
        if result.is_error:
            msg = text or "isError"
            raise McpToolError(f"MCP server {self._cfg.name!r} 调用 {name!r} 返回错误：{msg}")
        return text

    async def close(self) -> None:
        """关闭会话与传输（SDK 负责 stdio 子进程 terminate/kill 兜底，FR-014）。

        幂等：未连接 / 连接失败态也可安全调用。
        """
        session, transport = self._session, self._transport
        self._session = None
        self._transport = None
        if session is not None:
            await _safe_exit(session, f"MCP session {self._cfg.name}")
        if transport is not None:
            await _safe_exit(transport, f"MCP transport {self._cfg.name}")

    def _require_session(self) -> ClientSession:
        """未连接则抛 McpServerUnavailableError（fail-closed）。"""
        if self._session is None:
            raise McpServerUnavailableError(f"MCP server {self._cfg.name!r} 未连接")
        return self._session

    def _map_sdk_error(self, exc: MCPError, op: str) -> NoReturn:
        """SDK MCPError → 连接层 / 应用层分级异常（FR-011/FR-016）。"""
        if exc.code in (_MCP_CONNECTION_CLOSED, _MCP_REQUEST_TIMEOUT):
            raise McpServerUnavailableError(
                f"MCP server {self._cfg.name!r} {op}失败：{exc.message}", cause=exc
            ) from exc
        raise McpToolError(
            f"MCP server {self._cfg.name!r} {op}失败：{exc.message}", code=exc.code
        ) from exc


def _extract_text(content: Sequence[Any]) -> str:
    """拼接 content 中全部 TextContent.text（FR-015）。"""
    return "".join(item.text for item in content if isinstance(item, TextContent))


async def _safe_exit(cm: Any, label: str) -> None:
    """退出 async 上下文管理器，异常仅记录（关闭路径不抛）。"""
    try:
        await cm.__aexit__(None, None, None)
    except Exception as exc:
        logger.debug("%s 退出异常：%s", label, exc)
