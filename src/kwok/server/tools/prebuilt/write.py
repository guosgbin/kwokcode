from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel

from kwok.server.tools.context import cwd_var, read_files_var
from kwok.server.tools.tool import (
    PermissionLevel,
    ReadWrite,
    RiskLevel,
    Tool,
    ToolCategory,
    ToolError,
)


class WriteParams(BaseModel):
    path: str
    content: str


class WriteResult(BaseModel):
    path: str
    overwritten: bool


class WriteTool(Tool):
    name = "write"
    description = (
        "创建新文件或用完整内容覆盖已读取的现有文件（不追加、不合并）。"
        "覆盖现有文件前必须先使用 read_file 读取过该文件。"
    )
    input_model = WriteParams
    output_model = WriteResult
    permission_level: PermissionLevel = PermissionLevel.ASK
    risk_level: RiskLevel = RiskLevel.MEDIUM
    category: ToolCategory = ToolCategory(business_type="file", read_write=ReadWrite.WRITE)

    def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        raw_path = str(args["path"])
        content = str(args["content"])

        cwd = cwd_var.get() or "."
        path = (
            os.path.realpath(os.path.join(cwd, raw_path))
            if not os.path.isabs(raw_path)
            else os.path.realpath(raw_path)
        )

        exists = os.path.exists(path)
        if exists:
            read_set = read_files_var.get() or set()
            if path not in read_set:
                raise ToolError({
                    "error": (
                        f"无法覆盖未读取的文件 {path}。"
                        f"请先使用 read_file 读取该文件内容后再执行覆盖；"
                        f"若只想修改部分内容，请使用 Edit 工具。"
                    )
                })

        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

        read_set = read_files_var.get()
        if read_set is not None:
            read_set.add(path)
        return {"path": path, "overwritten": exists}