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
        ## 项目记忆写入规则
        将关键事实持久化写入当前项目的 memory 目录，本项目所有后续会话均可读取复用。
        适用内容：项目架构约定、重要技术决策、用户长期编码偏好、业务常驻事实、踩坑经验。
        不适合存放：单次会话临时信息、转瞬即逝的临时数据。
        
        1. 生成简短概括性标题，用于文件命名/索引，便于后续快速检索；
        2. **执行写入之前，必须先读取项目下已有的全部记忆文档；**
        3. 如果发现已有记忆存在相同/相近主题：
           - 对比新旧信息；
           - 执行更新、合并修正，禁止直接新增重复条目；
           - 处理新旧信息冲突，以最新事实为准；
        4. 不要碎片化大量写入，多条同类事实尽量收敛到同一文档；
        5. 只记录长期有效信息，不要保存临时会话上下文。
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
