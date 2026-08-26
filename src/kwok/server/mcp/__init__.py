"""MCP（Model Context Protocol）接入域：把外部 MCP 工具暴露为系统内普通 ``Tool``。

五层职责（spec: specs/mcp/spec.md）：
    配置层  load_mcp_config()：~/.kwok/mcp.json + .kwok/mcp.json 双层叠加、严格校验
    管理层  McpServerManager：start_all / stop_all / get_tools / register_tools
    协议层  McpClient：官方 mcp-sdk ClientSession 封装（stdio / Streamable HTTP 双传输）
    适配层  McpTool：{server}__{tool} 命名，schema 透传，调用拼接 text
    调用链  与普通工具同走 tool_execute 治理链（参数校验 → S5 权限 → 执行 → 事件）

消费方统一从这里 import：
    from kwok.server.mcp import load_mcp_config, McpServerManager, McpTool
"""
from kwok.server.mcp.config import load_mcp_config
from kwok.server.mcp.manager import McpServerManager
from kwok.server.mcp.tool import McpTool

__all__ = ["load_mcp_config", "McpServerManager", "McpTool"]
