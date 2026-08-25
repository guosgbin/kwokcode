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

_MAX_FILE_SIZE = 64 * 1024


class EditParams(BaseModel):
    path: str
    old_string: str
    new_string: str
    replace_all: bool = False


class EditResult(BaseModel):
    path: str
    replaced: int
    before: str
    after: str


class EditTool(Tool):
    name = "edit"
    description = (
        "对文件执行精确字符串替换：把 old_string 替换为 new_string（不用正则/模糊匹配）。"
        "old_string 必须与文件内容完全匹配且唯一；出现多次时需提供更长上下文或设置 replace_all=true。"
        "必须先读取该文件才能编辑。"
    )
    input_model = EditParams
    output_model = EditResult
    permission_level: PermissionLevel = PermissionLevel.ASK
    risk_level: RiskLevel = RiskLevel.MEDIUM
    category: ToolCategory = ToolCategory(business_type="file", read_write=ReadWrite.WRITE)

    def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        raw_path = str(args["path"])
        old_string = str(args["old_string"])
        new_string = str(args["new_string"])
        replace_all = bool(args.get("replace_all", False))

        cwd = cwd_var.get() or "."
        path = (
            os.path.realpath(os.path.join(cwd, raw_path))
            if not os.path.isabs(raw_path)
            else os.path.realpath(raw_path)
        )

        # 编辑前读取检查：文件必须先被完整读取（read_file 的 PARTIAL 不计数）
        read_set = read_files_var.get() or set()
        if path not in read_set:
            raise ToolError({
                "error": (
                    f"无法编辑未读取的文件 {path}。"
                    f"请先使用 read_file 完整读取该文件内容后再编辑。"
                )
            })

        try:
            size = os.path.getsize(path)
        except OSError as exc:
            raise ToolError({"error": f"edit 失败：{exc}"}) from exc
        if size > _MAX_FILE_SIZE:
            raise ToolError({
                "error": (
                    f"文件 {path} 超过 {_MAX_FILE_SIZE / 1024:.2f} KB 限制，"
                    f"请使用 read_file 定位内容后重试"
                )
            })

        try:
            with open(path, encoding="utf-8") as f:
                content = f.read()
        except OSError as exc:
            raise ToolError({"error": f"edit 失败：{exc}"}) from exc

        count = content.count(old_string)
        if count == 0:
            raise ToolError({
                "error": (
                    f"old_string 未在文件 {path} 中出现原文，请核对大小写与空格/缩进。"
                )
            })
        if count > 1 and not replace_all:
            raise ToolError({
                "error": (
                    f"old_string 在文件 {path} 中出现 {count} 次，不唯一。"
                    f"请提供更长、含更多上下文的 old_string，或设置 replace_all=true 全部替换。"
                )
            })

        new_content = content.replace(old_string, new_string)
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)

        if read_set is not None:
            read_set.add(path)
        return {
            "path": path,
            "replaced": count,
            "before": content,
            "after": new_content,
        }