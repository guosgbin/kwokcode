from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from kwok.protocol.events import BaseEvent, LLMUsageEvent
from kwok.server.event import EventBusManager
from kwok.server.llm.llm_context import LlmContext
from kwok.server.llm.model import LlmResponse
from kwok.server.llm.provider.llm_provider import LlmProvider

logger = logging.getLogger(__name__)

_SUMMARY_FILENAME_PREFIX = "summary_"

# 时间戳格式：summary 文件名与 transcript 备份文件名共用（纯时间戳方案）。
# 一次生成、两处复用，保证同次压缩的 summary_<ts>.md 与 <name>.jsonl.<ts>.bak 可配对审计。
_TS_FORMAT = "%Y%m%d-%H%M%S-%f"

_COMPACTION_PROMPT = """请把以下对话压缩为面向接手执行的下一个 LLM 实例的交接摘要，
省略推理过程，保留结论。严格按六段输出：

## Original Goal
一句话说明用户要什么。

## Completed Steps
已完成的工作（含文件路径 / 命令 / 决策）。

## Key Constraints
影响后续执行的事实。

## Current File State
每个文件的当前状态。

## Remaining TODOs
剩余工作（按优先级排序）。

## Critical Data
必须原样保留的值（ID / token / 报错信息等）。

对话历史：
{history}
"""


@dataclass
class CompactResult:
    """一次 L5 压缩的产物：摘要文本 / 留档路径 / 替换后的消息序列 / 摘要真实 token、
    展示用 saved_tokens 及共享时间戳 ts（summary 文件名与 transcript 备份文件名同款）。"""

    summary_text: str
    summary_path: Path
    compacted_messages: list[dict[str, Any]]
    token_count: int
    saved_tokens: int
    ts: str


class Compactor:
    """L5 LLM 摘要压缩核心：滑动窗口切分 + 六段式交接摘要 + 拼装合法消息序列。

    手动 /compact 与自动压缩共用本入口。压缩 LLM 调用走静默总线（只注册内部
    usage 采集器），不污染主 run 事件流。
    """

    @staticmethod
    def split_window(
        messages: list[dict[str, Any]], keep_recent: int
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """按最近 keep_recent 个 user 消息切分消息序列，返回 (older, recent_window)。

        窗口在 user 消息边界切分：recent_window 为最近 keep_recent 个 user 消息及其后续
        全部消息；此前更早的为 older。user 消息数 ≤ keep_recent 时无可压缩的更早历史，
        返回 ([], messages)。
        """
        if keep_recent < 1:
            keep_recent = 1
        user_indexes = [i for i, m in enumerate(messages) if m.get("role") == "user"]
        if len(user_indexes) <= keep_recent:
            return [], messages
        cut = user_indexes[-keep_recent]
        return messages[:cut], messages[cut:]

    async def compact_messages(
        self,
        provider: LlmProvider,
        messages: list[dict[str, Any]],
        *,
        keep_recent: int,
        session_dir: Path,
        turn_id: str = "",
    ) -> CompactResult:
        """对更早历史生成六段式交接摘要，返回 `[user_summary, assistant_ack, *recent_window]`。

        older 为空（无可压缩更早历史）时抛 ValueError，调用方应先做前置跳过。
        """
        older, recent_window = self.split_window(messages, keep_recent)
        if not older:
            raise ValueError("无可压缩的更早历史（user 消息 ≤ keep_recent）")
        # 时间戳一次生成、两处复用：summary_<ts>.md 文件名与 transcript 备份
        # <session-id>.jsonl.<ts>.bak 共享同一 ts，便于审计一一配对。
        ts = datetime.now().strftime(_TS_FORMAT)
        summary, token_count = await self._summarize(provider, older, turn_id=turn_id)
        compacted_messages: list[dict[str, Any]] = [
            {"role": "user", "content": summary},
            {"role": "assistant", "content": "Understood, I'll continue from this summary."},
            *recent_window,
        ]
        summary_path = self._write_summary(session_dir, summary, ts=ts)
        older_chars = sum(len(str(m.get("content") or "")) for m in older)
        saved_tokens = max(0, older_chars // 4 - token_count)
        return CompactResult(
            summary_text=summary,
            summary_path=summary_path,
            compacted_messages=compacted_messages,
            token_count=token_count,
            saved_tokens=saved_tokens,
            ts=ts,
        )

    async def _summarize(
        self, provider: LlmProvider, older: list[dict[str, Any]], turn_id: str
    ) -> tuple[str, int]:
        """对 older 历史做单次摘要调用：静默总线采集真实 completion_tokens，返回
        (摘要文本, token 数)。"""
        history = "\n".join(json.dumps(m, ensure_ascii=False) for m in older)
        prompt = _COMPACTION_PROMPT.format(history=history)
        capture: dict[str, int] = {}

        async def _on_usage(event: BaseEvent) -> None:
            if isinstance(event, LLMUsageEvent):
                capture["completion_tokens"] = event.output_tokens

        silent_bus = EventBusManager()
        silent_bus.subscribe(_on_usage)
        context = LlmContext(
            turn_id=turn_id or "compact",
            prompt=prompt,
            bus=silent_bus,
            max_steps=1,
            messages=[{"role": "user", "content": prompt}],
            session_id="",
        )
        resp: LlmResponse = await provider.stream_chat(context)
        return resp.text, capture.get("completion_tokens", 0)

    @staticmethod
    def _write_summary(session_dir: Path, summary: str, *, ts: str) -> Path:
        """写 summary_<ts>.md 到 session 目录（审计留档），返回路径。

        ts 由 compact_messages 一次生成（与 transcript 备份文件名共享同一 ts）。
        """
        path = session_dir / f"{_SUMMARY_FILENAME_PREFIX}{ts}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(summary, encoding="utf-8")
        logger.info("压缩摘要已落盘：%s", path)
        return path
