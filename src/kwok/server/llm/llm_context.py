from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from kwok.server.event import EventBusManager

_BASE_SYSTEM_PROMPT = """
你是Kwok‑Code，本地交互式编程代理，协助用户完成软件工程任务。

## 能力
你可以读取、编辑、新建文件，执行shell命令，搜索代码，排查和修复问题。优先使用工具获取信息，不要凭空猜测项目内容。

## 文件操作
- 局部修改优先使用 edit。
- 新建文件或大规模重写使用 write。
- write覆盖已有文件前，必须完整读取该文件；仅部分读取不允许全量覆写。

## Bash
- cd会跨命令保持工作目录。
- 禁止运行交互式程序。
- 输出过长，将输出重定向写入文件，再读取文件。

## 工具行为
- 严格尊重工具返回结果，工具报错基于报错处理，不要忽略错误继续执行。
- 工具会受权限控制，高危操作需要用户批准。

## 输出风格
直奔主题，文字输出尽量简短。优先执行动作，减少前置铺垫。不要复述用户指令。需要解释只输出必要信息。
"""


@dataclass
class LlmContext:
    turn_id: str
    prompt: str
    bus: EventBusManager
    max_steps: int = 20
    messages: list[dict[str, Any]] = field(default_factory=list)
    step: int = 0
    status: str = "running"
    reason: str | None = None
    text: str = ""
    tools: list[dict[str, object]] = field(default_factory=list)
    session_id: str = ""
    system: str = ""
    project_memory_idx: str = ""

    def system_prompt(self) -> str:
        """返回当前 run 的 system prompt，必要时注入项目记忆索引。"""
        if not self.project_memory_idx.strip():
            return _BASE_SYSTEM_PROMPT
        return (
            _BASE_SYSTEM_PROMPT
            + "\n\n## Project Memory\n"
            + self.project_memory_idx.strip()
            + "\n\n读取项目记忆详情请调用 read_project_memory 工具。"
        )

