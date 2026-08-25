from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


_DEFAULT_CONTEXT_FILE_GLOBAL = "~/.kwok/KWOK.md"
_DEFAULT_CONTEXT_FILE_PROJECT = ".kwok/KWOK.md"

def load_context_file(path: Path) -> str:
    """读取静态上下文文件（Global/Project 分层记忆）。

    文件缺失或读取失败（OSError / 解码错误）时静默降级为空串，不影响 turn 启动。
    """
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        logger.warning("上下文文件读取失败，忽略：%s", path)
        return ""


def load_global_and_project() -> tuple[str, str]:
    """解析并读取 Global / Project 两层静态记忆。

    Global 路径展开用户目录；Project 路径相对 daemon 启动目录（非绝对路径时拼 os.getcwd()）。
    """
    global_path = Path(_DEFAULT_CONTEXT_FILE_GLOBAL).expanduser()
    project_raw = Path(_DEFAULT_CONTEXT_FILE_PROJECT)
    project_path = (
        project_raw if project_raw.is_absolute() else Path(os.getcwd()) / project_raw
    )
    return load_context_file(global_path), load_context_file(project_path)


__all__ = ["load_context_file", "load_global_and_project"]
