from __future__ import annotations

from typing import Any

from kwok.server.tools.tool import Tool, register


def _read_file(args: dict[str, Any]) -> str:
    path = str(args.get("path", ""))
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError as exc:
        return f"read_file 失败：{exc}"


read_file_tool = Tool(
    name="read_file",
    description="读取指定路径的本地文本文件内容并返回。",
    parameters={
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    },
    execute=_read_file,
)

register(read_file_tool)
