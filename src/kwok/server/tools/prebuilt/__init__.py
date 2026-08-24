from __future__ import annotations

from kwok.server.tools.prebuilt.read_file import read_file_tool
from kwok.server.tools.registry import ToolRegistry


def register_prebuilt(registry: ToolRegistry) -> None:
    """把内置预置工具注册进指定注册表（幂等：已注册则跳过）。"""
    for tool in (read_file_tool,):
        if not registry.has(tool.name):
            registry.register(tool)
