from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

SessionKind = Literal["interactive", "one-shot"]
SessionStatus = Literal["idle", "busy", "waiting", "terminated"]
NameSource = Literal["derived", "user"]


class SessionMeta(BaseModel):
    """会话元数据，对应 <session-dir>/session-meta.json 的单个 JSON 对象。"""

    pid: int
    sessionId: str
    cwd: str
    startedAt: int
    procStart: str
    version: str
    kind: SessionKind
    entrypoint: str
    name: str
    nameSource: NameSource
    status: SessionStatus
    updatedAt: int
    statusUpdatedAt: int
    endedAt: int | None = None
    procEnd: str | None = None
