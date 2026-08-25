from __future__ import annotations

from typing import TYPE_CHECKING

from kwok.server.tools.prebuilt.bash import BashTool
from kwok.server.tools.prebuilt.edit import EditTool
from kwok.server.tools.prebuilt.read_file import ReadFileTool
from kwok.server.tools.prebuilt.read_project_memory import ReadProjectMemoryTool
from kwok.server.tools.prebuilt.read_project_memory_idx import ReadProjectMemoryIdxTool
from kwok.server.tools.prebuilt.write import WriteTool
from kwok.server.tools.prebuilt.write_project_memory import WriteProjectMemoryTool
from kwok.server.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from kwok.server.session.store import SessionStore

_registry: ToolRegistry | None = None


def init_tool_registry(store: SessionStore | None = None) -> None:
    """server 启动时调用一次，注册所有内置工具。幂等，多次调用不重复注册。"""
    global _registry
    if _registry is not None:
        return
    _registry = ToolRegistry()
    _registry.register(BashTool())
    _registry.register(EditTool())
    _registry.register(ReadFileTool())
    _registry.register(WriteTool())
    if store is not None:
        _registry.register(ReadProjectMemoryIdxTool(store))
        _registry.register(ReadProjectMemoryTool(store))
        _registry.register(WriteProjectMemoryTool(store))


def get_tool_registry() -> ToolRegistry:
    if _registry is None:
        raise RuntimeError("ToolRegistry 未初始化，请先调用 init_tool_registry")
    return _registry
