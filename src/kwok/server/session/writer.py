from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import TextIO

from pydantic import ValidationError

from kwok.server.llm.model import AssistantMessage, ToolResultMessage, UserMessage
from kwok.server.session.transcript import TranscriptRecord, message_to_record

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    """当前时间，ISO 8601 毫秒带时区（与 turn_log_writer_bus 的 _now_iso 一致）。"""
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


class SessionTranscriptWriter:
    """会话 transcript 文件写入口：懒开句柄、追加记录、逐行 flush（全同步块）。"""

    def __init__(self, session_dir: Path, session_id: str) -> None:
        self._path = session_dir / f"{session_id}.jsonl"
        self._file: TextIO | None = None

    @property
    def path(self) -> Path:
        """transcript 文件路径。"""
        return self._path

    def append(
            self,
            event: UserMessage | AssistantMessage | ToolResultMessage,
            *,
            turn_id: str,
    ) -> None:
        """追加一条消息记录并 flush。"""
        record = message_to_record(event, turn_id=turn_id, ts=_now_iso())
        file = self._ensure_open()
        file.write(record.model_dump_json() + "\n")
        file.flush()

    def read_records(self) -> list[TranscriptRecord]:
        """读回会话全部记录（文件顺序）；文件缺失或某行损坏则跳过。"""
        if not self._path.is_file():
            return []
        records: list[TranscriptRecord] = []
        with self._path.open("r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(TranscriptRecord.model_validate_json(line))
                except ValidationError:
                    logger.warning("transcript 行解析失败，跳过：%s", line[:80])
        return records

    def rewrite(self, records: list[TranscriptRecord], *, ts: str) -> None:
        """全量重写 transcript：关 append 句柄 → 备份原文件 → 写入新记录 → 重开句柄。

        备份用纯时间戳命名 `<name>.jsonl.<ts>.bak`，与同次压缩的 `summary_<ts>.md`
        共享同一 ts（纯时间戳方案）：每次压缩各自留档、互不覆盖，不再有固定的
        `.jsonl.bak` 被反复覆盖。调用方必须提供 ts（压缩路径取 CompactResult.ts），
        缺 ts 直接抛错，杜绝静默覆盖备份。
        调用前提：无并发写（手动路径由 busy 校验 + 互斥锁保证，自动路径在 run 任务内串行）。
        """
        if not ts:
            raise ValueError("rewrite 需提供备份时间戳 ts（压缩路径从 CompactResult.ts 取）")
        if self._file is not None:
            self._file.close()
            self._file = None
        if self._path.is_file():
            os.replace(self._path, self._path.with_name(f"{self._path.name}.{ts}.bak"))
        with self._path.open("w", encoding="utf-8") as file:
            for record in records:
                file.write(record.model_dump_json() + "\n")
        self._ensure_open()

    def _ensure_open(self) -> TextIO:
        """懒开句柄（追加写）。"""
        if self._file is None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._file = self._path.open("a", encoding="utf-8")
            logger.info("transcript 落盘已就绪：%s", self._path)
        return self._file

    def close(self) -> None:
        """关闭句柄（幂等）。"""
        if self._file is not None:
            self._file.close()
            self._file = None
            logger.info("transcript 落盘已关闭：%s", self._path)
