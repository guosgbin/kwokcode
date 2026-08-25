from __future__ import annotations

from contextvars import ContextVar

cwd_var: ContextVar[str] = ContextVar("cwd", default="")
"""当前 turn 的工作目录，由 send_message() 在入口处注入。"""

read_files_var: ContextVar[set[str] | None] = ContextVar("read_files", default=None)
"""本次会话已读取过的文件（绝对路径集合），由 send_message() 注入会话级 set。"""