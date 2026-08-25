from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from kwok.config import get_config
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
    skill_prompt: str = ""
    project_memory_idx: str = ""
    global_ctx: str = ""
    project_ctx: str = ""
    session_dir: str = ""
    context_pct: float = 0.0

    def system_prompt(self) -> str:
        """返回当前 run 的 system prompt。

        存在 `skill_prompt` 时以其替换 base；Global → Project → 项目记忆索引三层照常拼接，
        空小节跳过——skill 提示词与记忆注入互不冲突。
        """
        text = self.skill_prompt.strip() or _BASE_SYSTEM_PROMPT
        if self.global_ctx.strip():
            text += "\n\n## Global Context\n" + self.global_ctx
        if self.project_ctx.strip():
            text += "\n\n## Project Context\n" + self.project_ctx
        if self.project_memory_idx.strip():
            text += (
                "\n\n## Project Memory\n"
                + self.project_memory_idx.strip()
                + "\n\n读取项目记忆详情请调用 read_project_memory 工具。"
            )
        return text

    def read_messages(self) -> list[dict[str, Any]]:
        """返回发送给 LLM 的截断视图：超长 tool 结果保留前段 + 省略提示。

        仅影响发送瞬间的副本，`self.messages`（内存态）与 transcript（持久态）保持全量。
        """
        compaction = get_config().compaction
        truncated: list[dict[str, Any]] = []
        for msg in self.messages:
            content = msg.get("content")
            if (
                msg.get("role") == "tool"
                and isinstance(content, str)
                and len(content) > compaction.tool_result_limit
            ):
                keep = compaction.tool_result_keep
                n = max(0, len(content) - keep)
                truncated.append(
                    {
                        **msg,
                        "content": (
                            content[:keep]
                            + f"[... {n} chars omitted. Full output in run events.]"
                        ),
                    }
                )
            else:
                truncated.append(msg)
        return truncated

