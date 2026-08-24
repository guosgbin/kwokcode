from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from kwok.server.tools.tool import Tool, ToolError


class ReadFileParams(BaseModel):
    """read_file 入参：目标文件路径。"""

    path: str


class ReadFileResult(BaseModel):
    """read_file 返回值结构：路径 + 文件内容。"""

    path: str
    content: str


def _read_file(args: dict[str, Any]) -> dict[str, Any]:
    path = str(args["path"])
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
    except OSError as exc:
        raise ToolError({"error": f"read_file 失败：{exc}"}) from exc
    return {"path": path, "content": content}


read_file_tool = Tool(
    name="read_file",
    description="读取指定路径的本地文本文件内容并返回。",
    input_model=ReadFileParams,
    output_model=ReadFileResult,
    execute=_read_file,
)

