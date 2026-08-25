from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel

from kwok.server.tools.context import read_files_var
from kwok.server.tools.tool import Tool, ToolError, PermissionLevel

_MAX_READ_SIZE = 16 * 1024
_MAX_FILE_SIZE = 64 * 1024


class ReadFileParams(BaseModel):
    path: str
    offset: int | None = None
    limit: int | None = None


class ReadFileResult(BaseModel):
    path: str
    content: str
    total_lines: int
    is_partial: bool = False


class ReadFileTool(Tool):
    name = "read"
    description = "读取指定路径的本地文本文件内容并返回。支持 offset/limit 分页读取大文件。"
    input_model = ReadFileParams
    output_model = ReadFileResult
    permission_level: PermissionLevel = PermissionLevel.ASK


    def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        result = self._do_read(args)
        if not result.get("is_partial"):
            self._mark_read(args["path"])
        return result

    def _do_read(self, args: dict[str, Any]) -> dict[str, Any]:
        path = str(args["path"])
        offset = args.get("offset")
        limit = args.get("limit")

        try:
            file_size = os.path.getsize(path)
        except OSError as exc:
            raise ToolError({"error": f"read_file 失败：{exc}"}) from exc

        if file_size > _MAX_FILE_SIZE:
            raise ToolError({
                "error": (
                    f"文件 {path} 超过 {_MAX_FILE_SIZE / 1024:.2f} KB 限制，"
                    f"请使用 Grep 工具搜索特定内容"
                )
            })

        try:
            with open(path, encoding="utf-8") as f:
                lines = f.readlines()
        except OSError as exc:
            raise ToolError({"error": f"read_file 失败：{exc}"}) from exc

        total_lines = len(lines)

        if total_lines == 0:
            return {
                "path": path,
                "content": f"<EMPTY_FILE: 文件 {path} 存在但内容为空>",
                "total_lines": 0,
                "is_partial": False,
            }

        if offset is not None and offset > total_lines:
            return {
                "path": path,
                "content": (
                    f"<OUT_OF_RANGE: 文件 {path} 共 {total_lines} 行，"
                    f"offset {offset} 超出范围>"
                ),
                "total_lines": total_lines,
                "is_partial": False,
            }

        start = (offset - 1) if offset is not None else 0
        end = min(start + limit, total_lines) if limit is not None else total_lines

        for i in range(start, end):
            if len(lines[i].encode("utf-8")) > _MAX_READ_SIZE:
                raise ToolError({
                    "error": (
                        f"第 {i + 1} 行过长（超过 {_MAX_READ_SIZE / 1024:.2f} KB），"
                        f"建议使用 Grep 搜索特定内容"
                    )
                })

        target_lines = lines[start:end]
        content = "".join(target_lines)
        content_bytes = len(content.encode("utf-8"))
        is_explicit = offset is not None or limit is not None

        if is_explicit and content_bytes > _MAX_READ_SIZE:
            raise ToolError({
                "error": (
                    f"指定范围超过 {_MAX_READ_SIZE / 1024:.2f} KB，"
                    f"请使用较小的 limit 或改用 Grep 搜索特定内容"
                )
            })

        if not is_explicit and content_bytes > _MAX_READ_SIZE:
            accumulated = 0
            cut_count = 0
            for line in target_lines:
                line_bytes = len(line.encode("utf-8"))
                if accumulated + line_bytes > _MAX_READ_SIZE:
                    break
                accumulated += line_bytes
                cut_count += 1
            target_lines = target_lines[:cut_count]
            content = "".join(target_lines)
            partial_hint = (
                f"<PARTIAL_VIEW: 文件 {path} 仅显示前 {cut_count} 行"
                f"（共 {total_lines} 行），约 {_MAX_READ_SIZE / 1024:.2f} KB。\n"
                f"请使用 read_file(path=\"{path}\", offset={cut_count + 1})"
                f" 继续读取后续内容。>"
            )
            return {
                "path": path,
                "content": self._format_lines(target_lines, start + 1) + "\n" + partial_hint,
                "total_lines": total_lines,
                "is_partial": True,
            }

        return {
            "path": path,
            "content": self._format_lines(target_lines, start + 1),
            "total_lines": total_lines,
            "is_partial": False,
        }

    @staticmethod
    def _mark_read(path: str) -> None:
        """把已成功读取的文件加入会话级已读集合（供 write 覆盖校验）。"""
        read_set = read_files_var.get()
        if read_set is not None:
            read_set.add(os.path.realpath(path))

    @staticmethod
    def _format_lines(lines: list[str], start_line: int) -> str:
        parts = []
        for i, line in enumerate(lines):
            line_num = start_line + i
            parts.append(f"{line_num}  | {line.rstrip(chr(10))}")
        return "\n".join(parts)
