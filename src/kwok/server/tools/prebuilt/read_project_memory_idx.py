from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from kwok.server.tools.context import cwd_var
from kwok.server.tools.tool import ReadWrite, RiskLevel, Tool, ToolCategory, ToolError, PermissionLevel

if TYPE_CHECKING:
    from kwok.server.session.store import SessionStore


class ReadProjectMemoryIdxParams(BaseModel):
    """read_project_memory_idx 无入参。"""

    pass


class ReadProjectMemoryIdxResult(BaseModel):
    """read_project_memory_idx 返回值：索引内容 + 文件路径。"""

    content: str
    path: str


class ReadProjectMemoryIdxTool(Tool):
    """read_project_memory_idx：读取当前项目的记忆索引文件 MEMORY.md。"""

    name = "read_project_memory_idx"
    description = "读取当前项目的记忆索引文件 MEMORY.md，返回所有已保存的记忆条目列表。"
    input_model = ReadProjectMemoryIdxParams
    output_model = ReadProjectMemoryIdxResult
    permission_level: PermissionLevel = PermissionLevel.ASK
    category = ToolCategory(business_type="memory", read_write=ReadWrite.READ)
    risk_level = RiskLevel.READONLY

    def __init__(self, store: SessionStore | None = None) -> None:
        self._store = store

    def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        if self._store is None:
            raise ToolError({"error": "read_project_memory_idx 失败：当前项目存储上下文未注入"})
        cwd = cwd_var.get()
        if not cwd:
            raise ToolError({"error": "read_project_memory_idx 失败：当前项目目录未注入"})
        index = self._store.memory_dir(cwd) / "MEMORY.md"
        try:
            content = index.read_text(encoding="utf-8") if index.is_file() else ""
        except OSError as exc:
            raise ToolError({"error": f"read_project_memory_idx 失败：{exc}"}) from exc
        return {"content": content, "path": str(index)}