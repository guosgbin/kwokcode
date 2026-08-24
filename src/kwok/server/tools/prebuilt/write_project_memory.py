from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from kwok.server.tools.context import cwd_var
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
    description = ("""
        持久化写入项目级长期记忆到memory目录，本项目未来所有会话可复用。
        适合：项目架构约定、技术决策、编码偏好、业务常驻事实、踩坑经验。
        禁止：会话临时信息、一次性临时草稿。
        
        强制流程：
        1. 先调用 read_project_memory_idx 读取MEMORY.md记忆索引；
        2. 根据索引判断有无相近主题记忆，有则调用 read_project_memory 读取原文档；
        3. 存在相近条目必须合并更新，禁止重复新建，冲突以最新事实为准；
        4. 使用简短概括标题作为文档名，便于检索；同类事实收敛到同一文档，避免大量碎片文件；
        5. 写入完成同步更新MEMORY.md索引，维护条目标题与文件名。
        仅保存长期跨会话有效知识，不记录会话临时上下文。
    """
                   )
    input_model = WriteProjectMemoryParams
    output_model = WriteProjectMemoryResult
    category = ToolCategory(business_type="memory", read_write=ReadWrite.WRITE)
    risk_level = RiskLevel.MEDIUM

    def __init__(self, store: SessionStore | None = None) -> None:
        self._session_store = store

    def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        name = str(args["name"]).strip()
        if not name:
            raise ToolError({"error": "write_project_memory 失败：记忆名不能为空"})
        content = str(args["content"])
        if self._session_store is None:
            raise ToolError({"error": "write_project_memory 失败：当前项目存储上下文未注入"})
        cwd = cwd_var.get()
        if not cwd:
            raise ToolError({"error": "write_project_memory 失败：当前项目目录未注入"})
        try:
            path = self._session_store.write_memory(
                cwd, name, content, summary=args.get("summary")
            )
        except OSError as exc:
            raise ToolError({"error": f"write_project_memory 失败：{exc}"}) from exc
        return {"name": name, "path": str(path)}
