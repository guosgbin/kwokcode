from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import TextIO

from kwok.protocol.events import BaseEvent

logger = logging.getLogger(__name__)

TURNS_DIR = Path("turns")


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


class TurnLogWriterBus:

    def __init__(self, turn_id: str) -> None:
        self._path = TURNS_DIR / turn_id / "event.jsonl"
        self._file: TextIO | None = None

    @property
    def path(self) -> Path:

        return self._path

    async def on_event(self, event: BaseEvent) -> None:

        line = json.dumps({"ts": _now_iso(), **event.model_dump()}, ensure_ascii=False)
        file = self._ensure_open()
        file.write(line + "\n")
        file.flush()

    def _ensure_open(self) -> TextIO:

        if self._file is None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._file = self._path.open("a", encoding="utf-8")
            logger.info("turn 日志落盘已就绪：%s", self._path)
        return self._file

    def close(self) -> None:

        if self._file is not None:
            self._file.close()
            self._file = None
            logger.info("turn 日志落盘已关闭：%s", self._path)

    async def __aenter__(self) -> TurnLogWriterBus:

        return self

    async def __aexit__(self, *exc_info: object) -> None:
        self.close()
