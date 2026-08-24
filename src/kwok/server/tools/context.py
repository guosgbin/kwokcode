from __future__ import annotations

from contextvars import ContextVar

cwd_var: ContextVar[str] = ContextVar("cwd", default="")
"""当前 turn 的工作目录，由 send_message() 在入口处注入。"""