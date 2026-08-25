from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from kwok.server.tools.context import cwd_var
from kwok.server.tools.tool import ReadWrite, RiskLevel, Tool, ToolCategory, ToolError, PermissionLevel

if TYPE_CHECKING:
    from kwok.server.session.store import SessionStore


class ReadProjectMemoryParams(BaseModel):
    """read_project_memory 入参：记忆名。"""

    name: str


class ReadProjectMemoryResult(BaseModel):
    """read_project_memory 返回值：记忆名 + 内容 + 文件路径。"""

    name: str
    content: str
    path: str


class ReadProjectMemoryTool(Tool):
    """read_project_memory：读取指定名称的项目记忆文件内容。"""

    name = "read_project_memory"
    description = "读取指定名称的项目记忆文件内容，name 参数为记忆名（不含 .md 后缀）。"
    input_model = ReadProjectMemoryParams
    output_model = ReadProjectMemoryResult
    permission_level: PermissionLevel = PermissionLevel.ASK
    category = ToolCategory(business_type="memory", read_write=ReadWrite.READ)
    risk_level = RiskLevel.READONLY

    def __init__(self, store: SessionStore | None = None) -> None:
        self._store = store

    def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        name = str(args["name"]).strip()
        if not name:
            raise ToolError({"error": "read_project_memory 失败：记忆名不能为空"})
        if self._store is None:
            raise ToolError({"error": "read_project_memory 失败：当前项目存储上下文未注入"})
        cwd = cwd_var.get()
        if not cwd:
            raise ToolError({"error": "read_project_memory 失败：当前项目目录未注入"})
        target = self._store.memory_path(cwd, name)
        if not target.is_file():
            raise ToolError({"error": f"read_project_memory 失败：记忆文件不存在 - {name}"})
        try:
            content = target.read_text(encoding="utf-8")
        except OSError as exc:
            raise ToolError({"error": f"read_project_memory 失败：{exc}"}) from exc
        return {"name": name, "content": content, "path": str(target)}