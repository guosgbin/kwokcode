from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from kwok.server.tools.tool import ReadWrite, RiskLevel, Tool, ToolCategory, ToolError

if TYPE_CHECKING:
    from kwok.server.session.store import SessionStore


class WriteProjectMemoryParams(BaseModel):
    """write_project_memory 入参：记忆名 + 正文（+ 可选摘要，缺省取正文首行）。"""

    name: str
    content: str
    summary: str | None = None


class WriteProjectMemoryResult(BaseModel):
    """write_project_memory 返回值：写入的记忆名 + 落盘路径。"""

    name: str
    path: str


class WriteProjectMemoryTool(Tool):
    """write_project_memory：把一条记忆写入当前项目的项目级缓存（memory 目录）。"""

    name = "write_project_memory"
    description = (
        "把一条记忆写入当前项目的项目级缓存（memory 目录），供未来会话复用。"
        "适用于沉淀用户偏好、项目约定、常驻事实等。"
    )
    input_model = WriteProjectMemoryParams
    output_model = WriteProjectMemoryResult
    category = ToolCategory(business_type="memory", read_write=ReadWrite.WRITE)
    risk_level = RiskLevel.MEDIUM

    def __init__(self, store: SessionStore | None = None, cwd: str | None = None) -> None:
        self._session_store = store
        self.cwd = cwd

    def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        name = str(args["name"]).strip()
        if not name:
            raise ToolError({"error": "write_project_memory 失败：记忆名不能为空"})
        content = str(args["content"])
        if self._session_store is None:
            raise ToolError({"error": "write_project_memory 失败：当前项目存储上下文未注入"})
        if not self.cwd:
            raise ToolError({"error": "write_project_memory 失败：当前项目目录未注入"})
        try:
            path = self._session_store.write_memory(
                self.cwd, name, content, summary=args.get("summary")
            )
        except OSError as exc:
            raise ToolError({"error": f"write_project_memory 失败：{exc}"}) from exc
        return {"name": name, "path": str(path)}
