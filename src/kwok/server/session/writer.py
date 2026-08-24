from __future__ import annotations

import logging
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
