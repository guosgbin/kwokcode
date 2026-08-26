"""管理层：MCP server 生命周期与工具注册（plan D6，FR-003/FR-005/FR-006/FR-014）。

McpServerManager 在 daemon 启动时逐个 server 连接 → 发现工具 → 包装为
``McpTool`` 缓存；单点失败 log 跳过（FR-005）；工具发现只做一次（FR-006）；
停机一次性清理全部 client（FR-014）。注册动作由 app 启动时调用一次
（与全局单例 ``ToolRegistry`` 调和，FR-018，plan D7）。
"""
from __future__ import annotations

import logging

from kwok.config import McpServerConfig
from kwok.server.mcp.client import McpClient
from kwok.server.mcp.tool import McpTool
from kwok.server.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class McpServerManager:
    """管理多个 MCP server 生命周期与已发现工具缓存。"""

    def __init__(self, read_timeout: float = 30.0) -> None:
        self._read_timeout = read_timeout
        self._clients: list[McpClient] = []
        self._tools: list[McpTool] = []

    async def start_all(self, servers: list[McpServerConfig]) -> None:
        """逐个连接 + 发现工具 + 缓存；单点失败 log 跳过（FR-005）。"""
        for cfg in servers:
            try:
                await self._start_one(cfg)
            except Exception as exc:
                logger.exception("MCP server %r 启动失败，跳过：%s", cfg.name, exc)

    async def _start_one(self, cfg: McpServerConfig) -> None:
        client = McpClient(cfg, read_timeout=self._read_timeout)
        await client.connect()  # 失败时内部已清理，且不进入 _clients
        self._clients.append(client)  # connect 成功即登记，list_tools 失败也由 stop_all 清理
        tools = await client.list_tools()
        for tool_def in tools:
            self._tools.append(McpTool(cfg.name, tool_def, client))
        logger.info("%s connected, %d tool(s)", cfg.name, len(tools))

    def get_tools(self) -> list[McpTool]:
        """已发现工具（启动时缓存，运行期不反复请求，FR-006）。"""
        return list(self._tools)

    def register_tools(self, registry: ToolRegistry) -> None:
        """把已发现工具逐个注册进 registry（FR-018；仅启动时调用一次）。"""
        for tool in self._tools:
            registry.register(tool)

    async def stop_all(self) -> None:
        """关闭全部 client，异常静默；清空缓存（FR-014）。

        注意：不可用 ``asyncio.gather(client.close(), ...)`` 并发关闭——SDK
        ClientSession 在调用方 task 内 enter 的 anyio cancel scope 有 task 亲和性，
        gather 把 close 挪进新 task 退出会死锁（stop_all 永远不返回）。顺序 close
        与 start_all 同 task，规避该问题；N 小且 close 有界（SDK ~5s 上限），顺序足够。
        """
        for client in self._clients:
            try:
                await client.close()
            except Exception:
                logger.debug("%s close 异常（已忽略）", client, exc_info=True)
        self._clients.clear()
        self._tools.clear()
