"""工具适配层：把 MCP server 工具包装为系统内普通 ``Tool``（plan D5，FR-007）。

``McpTool`` 以 ``{server}__{tool}`` 命名防跨 server 冲突（OQ-2），透传服务端
``inputSchema`` 作为 OpenAI function parameters，并以宽松 ``_PassthroughArgs``
模型同时满足 ``ToolRegistry.register`` 与 ``ToolParamCheckMiddleware`` 的
``input_model`` 非空约束（真实参数校验由 MCP server 承担）。调用经
``McpClient.call_tool`` 拼接 text 返回（FR-015）；``strict=True``（部分 provider
只接受 strict function tool，透传 schema 经 ``_sanitize_schema`` 归一化为
strict 合规后安全开启，可选字段退化为必填）；权限级别 ``ASK``（S5 权限审批
自动覆盖，FR-017）；覆写 ``execute_async``（runner 检测到覆写后在事件循环内
await，FR-010 串行性由 SDK 会话保证）。名字经 ``_safe_name`` 限制到
``[a-zA-Z0-9_-]``（部分 provider 拒绝冒号等字符，如 OpenAI function name 校验）。
"""
from __future__ import annotations

import re
from typing import Any, cast

from pydantic import BaseModel, ConfigDict

from kwok.server.mcp.client import McpClient, ToolDef
from kwok.server.tools.tool import PermissionLevel, Tool, ToolError


def _safe_name(value: str) -> str:
    """把名字限制到 provider 接受的字符集 ``[a-zA-Z0-9_-]``，其余替换为下划线。

    部分 LLM provider 校验 function name 必须匹配 ``^[a-zA-Z0-9_-]+$``，冒号等
    分隔符会整体 400 拒绝；替换后再以 ``{server}__{tool}`` 拼接（双下划线在字符
    集内，防跨 server 冲突）。``__`` 分隔可能被边界下划线撞车（如 server 以 _ 结尾
    且 tool 以 _ 开头），概率极低且 registry 重名守卫会在启动时报错暴露。
    """
    return re.sub(r"[^a-zA-Z0-9_-]", "_", value)


class _PassthroughArgs(BaseModel):
    """宽松透传入参模型：接受任意参数，真实校验由 MCP server 承担（plan D5）。"""

    model_config = ConfigDict(extra="allow")


# OpenAI function-calling 不支持的 JSON Schema 构造（plan D5 已知限制，T014）：
# 个别 MCP server 的 inputSchema 会带 $schema/definitions/$ref 等，直接透传给
# provider 可能被拒（400）。剥除后做保守降级，而非拦截整个 server。
_OPENAI_UNSUPPORTED_SCHEMA_KEYS = frozenset(
    {"$schema", "$defs", "definitions", "$ref", "patternProperties"}
)


def _sanitize_schema(node: Any) -> Any:
    """归一化为 OpenAI strict 兼容 schema：剥除不支持构造 + 强制 strict 约束。

    剥除 ``$schema``/``definitions``/``$ref`` 等（T014）——``$ref`` 与其定义容器
    一起剥除，避免悬空引用，被拆的属性退化为 ``{}``（任意类型）。同时给每个
    含 ``properties`` 的 object 加 ``additionalProperties: false`` 并把全部
    properties 并入 ``required``，满足 strict 模式（禁止额外键 + 字段必填）；
    MCP server 的可选字段因此退化为必填，是可接受的降级而非 provider 400 拒绝。
    """
    if isinstance(node, dict):
        result = {
            key: _sanitize_schema(value)
            for key, value in node.items()
            if key not in _OPENAI_UNSUPPORTED_SCHEMA_KEYS
        }
        properties = result.get("properties")
        if isinstance(properties, dict):
            result.setdefault("additionalProperties", False)
            required = result.get("required")
            merged = list(required) if isinstance(required, list) else []
            for key in properties:
                if key not in merged:
                    merged.append(key)
            if merged:
                result["required"] = merged
        return result
    if isinstance(node, list):
        return [_sanitize_schema(item) for item in node]
    return node


class McpTool(Tool):
    """MCP server 工具的 Tool 接口适配器（FR-007/FR-015/FR-017）。"""

    strict = True  # schema 经 _sanitize_schema 归一化为 strict 合规后开启
    permission_level: PermissionLevel = PermissionLevel.ASK
    input_model: type[BaseModel] = _PassthroughArgs

    def __init__(self, server_name: str, tool_def: ToolDef, client: McpClient) -> None:
        self._server_name = server_name
        self._tool_def = tool_def
        self._tool_name = str(tool_def["name"])
        self._client = client
        self.name = f"{_safe_name(server_name)}__{_safe_name(self._tool_name)}"
        desc = tool_def.get("description")
        self.description = (
            desc if isinstance(desc, str) and desc.strip() else f"MCP 工具：{self.name}"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        """透传服务端 inputSchema 作入参 schema（FR-007，T014 归一化）。"""
        schema = self._tool_def.get("input_schema")
        if isinstance(schema, dict):
            return cast(dict[str, Any], _sanitize_schema(schema))
        return {}

    def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        """同步执行不可用：MCP SDK 为 asyncio，runner 已切到 execute_async。"""
        raise ToolError({"error": f"MCP 工具 {self.name} 仅支持异步执行（execute_async）"})

    async def execute_async(self, args: dict[str, Any]) -> str:
        """事件循环内调用 MCP server，拼接 text 返回（FR-015）。"""
        return await self._client.call_tool(self._tool_name, args)
