from __future__ import annotations

from collections.abc import Sequence

from kwok.server.tools.tool import Tool


class ToolRegistry:
    """工具注册表：register / get / has / find / search / schemas / all。"""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        name = tool.name
        if not name or not name.strip():
            raise ValueError("工具名不能为空或全空白")
        if not tool.description or not tool.description.strip():
            raise ValueError(f"工具 {name!r} 缺少 description")
        if tool.input_model is None:
            raise ValueError(f"工具 {name!r} 缺少 input_model")
        if name in self._tools:
            raise ValueError(f"工具重名：{name}")
        self._tools[name] = tool

    def get(self, name: str) -> Tool | None:
        """按名取工具，不存在返回 None。"""
        return self._tools.get(name)

    def schemas(self, tools: Sequence[Tool] | None = None) -> list[dict[str, object]]:
        """导出 OpenAI function schema 列表；tools 为 None 时导出全部已注册工具。"""
        items = list(tools) if tools is not None else list(self._tools.values())
        return [t.schema for t in items]
