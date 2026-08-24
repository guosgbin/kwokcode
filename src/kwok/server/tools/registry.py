from __future__ import annotations

from collections.abc import Sequence

from kwok.server.tools.tool import PermissionLevel, ReadWrite, RiskLevel, Tool


class ToolRegistry:
    """工具注册表：register / get / has / find / search / schemas / all。"""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """登记工具；重名、空名/空白名、空说明拒绝（fail-fast）。

        input_model 与 execute 为 Tool 构造必填项，由类型系统保证存在，此处校验运行时可达项。
        """
        name = tool.name
        if not name or not name.strip():
            raise ValueError("工具名不能为空或全空白")
        if not tool.description or not tool.description.strip():
            raise ValueError(f"工具 {name!r} 缺少 description")
        if name in self._tools:
            raise ValueError(f"工具重名：{name}")
        self._tools[name] = tool

    def get(self, name: str) -> Tool | None:
        """按名取工具，不存在返回 None。"""
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        """按名判断是否存在。"""
        return name in self._tools

    def find(
        self,
        *,
        business_type: str | None = None,
        read_write: ReadWrite | None = None,
        risk_level: RiskLevel | None = None,
        permission_level: PermissionLevel | None = None,
    ) -> list[Tool]:
        """按分类与安全字段组合过滤，返回同时满足全部条件的子集。"""
        result = list(self._tools.values())
        if business_type is not None:
            result = [t for t in result if t.category.business_type == business_type]
        if read_write is not None:
            result = [t for t in result if t.category.read_write == read_write]
        if risk_level is not None:
            result = [t for t in result if t.risk_level == risk_level]
        if permission_level is not None:
            result = [t for t in result if t.permission_level == permission_level]
        return result

    def search(self, query: str) -> list[Tool]:
        """对 name / description / business_type 做大小写不敏感子串匹配。"""
        q = query.lower()
        return [
            t
            for t in self._tools.values()
            if q in t.name.lower()
            or q in t.description.lower()
            or q in t.category.business_type.lower()
        ]

    def schemas(self, tools: Sequence[Tool] | None = None) -> list[dict[str, object]]:
        """导出 OpenAI function schema 列表；tools 为 None 时导出全部已注册工具。"""
        items = list(tools) if tools is not None else list(self._tools.values())
        return [t.schema for t in items]

    def all(self) -> list[Tool]:
        """全部已注册工具。"""
        return list(self._tools.values())


_tool_registry: ToolRegistry | None = None


def init_tool_registry() -> ToolRegistry:
    """幂等初始化工具注册表单例。"""
    global _tool_registry
    if _tool_registry is not None:
        return _tool_registry
    _tool_registry = ToolRegistry()
    return _tool_registry


def get_tool_registry() -> ToolRegistry:
    """取进程级工具注册表单例（未初始化则抛错）。"""
    if _tool_registry is None:
        raise RuntimeError("工具注册表未初始化：请先调用 init_tool_registry()")
    return _tool_registry


def reset_tool_registry() -> None:
    """重置单例（测试隔离用）。"""
    global _tool_registry
    _tool_registry = None
