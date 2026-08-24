from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kwok import __version__
from kwok.protocol.errors import LlmError
from kwok.server.event import get_bus
from kwok.server.llm.loop import run
from kwok.server.llm.model import AssistantMessage, ToolResultMessage, UserMessage
from kwok.server.llm.provider.llm_provider import LlmProvider
from kwok.server.session.meta import NameSource, SessionKind, SessionMeta, SessionStatus
from kwok.server.session.name import derive_name
from kwok.server.session.store import SessionStore
from kwok.server.session.transcript import records_to_messages
from kwok.server.session.writer import SessionTranscriptWriter
from kwok.util.id_generator import gen_session_id, gen_turn_id

logger = logging.getLogger(__name__)


def _now_ms() -> int:
    """当前毫秒级 unix 时间戳（js 风格）。"""
    return int(time.time() * 1000)


def _now_ctime() -> str:
    """当前人类可读时间（time.ctime() 风格）。"""
    return time.ctime()


def _pid_alive(pid: int) -> bool:
    """用 os.kill(pid, 0) 探测进程是否存活。"""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


@dataclass
class Session:
    """运行中的会话：元数据 + 归属连接 + transcript 写入口 + 目录。"""

    id: str
    owner_connection_id: str
    meta: SessionMeta
    transcript_writer: SessionTranscriptWriter
    dir: Path


class SessionManager:
    """会话生命周期编排：注册表 + 状态机 + transcript + 孤儿回收。"""

    def __init__(
        self,
        *,
        store: SessionStore,
        get_provider: Callable[[], LlmProvider | None],
        version: str = __version__,
    ) -> None:
        self._store = store
        self._bus = get_bus()
        self._get_provider = get_provider
        self._version = version
        self._sessions: dict[str, Session] = {}
        self._turn_tasks: set[asyncio.Task[None]] = set()

    def create(
        self,
        *,
        mode: SessionKind,
        title: str,
        cwd: str,
        owner: str,
        name: str | None = None,
    ) -> Session:
        """新建会话：建目录、写 meta（idle）、登记 owner 绑定。"""
        session_id = gen_session_id()
        session_dir = self._store.session_dir(cwd, session_id)
        now_ms = _now_ms()
        meta_name: str
        name_source: NameSource
        if name and name.strip():
            meta_name = name.strip()
            name_source = "user"
        elif mode == "one-shot":
            meta_name = title[:40]
            name_source = "derived"
        else:
            meta_name = ""
            name_source = "derived"
        meta = SessionMeta(
            pid=os.getpid(),
            sessionId=session_id,
            cwd=cwd,
            startedAt=now_ms,
            procStart=_now_ctime(),
            version=self._version,
            kind=mode,
            entrypoint="cli",
            name=meta_name,
            nameSource=name_source,
            status="idle",
            updatedAt=now_ms,
            statusUpdatedAt=now_ms,
        )
        self._store.write_meta(session_dir, meta)
        writer = SessionTranscriptWriter(session_dir, session_id)
        session = Session(
            id=session_id,
            owner_connection_id=owner,
            meta=meta,
            transcript_writer=writer,
            dir=session_dir,
        )
        self._sessions[session_id] = session
        logger.info("会话已创建：%s kind=%s name=%r", session_id, mode, meta.name)
        return session

    def get_owned(self, session_id: str, owner: str) -> Session:
        """按 id + owner 取会话；不存在/非 owner 抛 LlmError。"""
        session = self._sessions.get(session_id)
        if session is None:
            raise LlmError("会话不存在")
        if session.owner_connection_id != owner:
            raise LlmError("会话不属于当前连接")
        return session

    def begin_turn(self, session_id: str, owner: str) -> Session:
        """校验 owner + busy/terminated，置 busy 并原子写 meta。"""
        session = self.get_owned(session_id, owner)
        if session.meta.status == "busy":
            raise LlmError("会话忙，请等上一轮结束")
        if session.meta.status == "terminated":
            raise LlmError("会话已结束")
        self._update_status(session, "busy")
        return session

    def launch_turn(self, session_id: str, prompt: str, owner: str) -> str:
        """begin_turn + 派生 turn_id + 后台执行 send_message，返回 turn_id（fire-and-forget）。"""
        self.begin_turn(session_id, owner)
        turn_id = gen_turn_id()
        task = asyncio.create_task(self.send_message(session_id, prompt, turn_id))
        self._turn_tasks.add(task)
        task.add_done_callback(self._turn_tasks.discard)
        return turn_id

    async def send_message(self, session_id: str, message: str, turn_id: str) -> None:
        """跑一轮完整 turn：读盘历史 → 写 user → 派生名 → LLM 循环 → 按 kind 收尾。"""
        session = self._sessions.get(session_id)
        if session is None:
            raise LlmError("会话不存在")
        history = self._history_messages(session)
        session.transcript_writer.append(UserMessage(message), turn_id=turn_id)
        if session.meta.kind == "interactive" and session.meta.name == "":
            session.meta.name = derive_name(message, 30)
            session.meta.updatedAt = _now_ms()
            self._store.write_meta(session.dir, session.meta)

        def on_message(msg: AssistantMessage | ToolResultMessage) -> None:
            session.transcript_writer.append(msg, turn_id=turn_id)

        try:
            provider = self._get_provider()
            if provider is None:
                raise LlmError("provider 未初始化")
            await run(
                provider,
                message,
                turn_id,
                turns_dir=session.dir / "turns",
                on_message=on_message,
                history=history,
            )
        finally:
            if session.meta.kind == "one-shot":
                self._terminate(session)
                session.transcript_writer.close()
            else:
                self._update_status(session, "idle")

    def _history_messages(self, session: Session) -> list[dict[str, Any]]:
        """读盘该会话全部历史记录，转 LLM wire 格式（不含本轮 user 消息）。"""
        return records_to_messages(session.transcript_writer.read_records())

    def close(self, session_id: str, owner: str) -> Session:
        """关闭会话：owner 校验 + 幂等 terminate + 关 writer。"""
        session = self.get_owned(session_id, owner)
        self._terminate(session)
        session.transcript_writer.close()
        return session

    def close_all(self) -> None:
        """daemon 停机：全部会话置 terminated 并关闭 writer。"""
        for session in list(self._sessions.values()):
            self._terminate(session)
            session.transcript_writer.close()

    def terminate_owned(self, connection_id: str) -> None:
        """连接断开：该连接拥有的全部会话置 terminated 并关闭 writer。"""
        for session in list(self._sessions.values()):
            if session.owner_connection_id == connection_id:
                self._terminate(session)
                session.transcript_writer.close()

    def scan_orphans(self) -> None:
        """回收孤儿会话：pid 非当前进程且不存活且非 terminated 的 meta 置 terminated。"""
        current_pid = os.getpid()
        projects_root = self._store.projects_dir
        if not projects_root.is_dir():
            return
        for project_dir in projects_root.iterdir():
            if not project_dir.is_dir():
                continue
            for session_dir in project_dir.iterdir():
                if not session_dir.is_dir():
                    continue
                meta = self._store.read_meta(session_dir)
                if meta is None or meta.status == "terminated":
                    continue
                if meta.pid == current_pid or _pid_alive(meta.pid):
                    continue
                meta.status = "terminated"
                now_ms = _now_ms()
                meta.endedAt = now_ms
                meta.procEnd = _now_ctime()
                meta.statusUpdatedAt = now_ms
                meta.updatedAt = now_ms
                self._store.write_meta(session_dir, meta)
                logger.info("孤儿会话已回收：%s（pid=%s）", meta.sessionId, meta.pid)

    def _update_status(self, session: Session, status: SessionStatus) -> None:
        """更新状态并原子写 meta（terminated 终态不再变更）。"""
        if session.meta.status == "terminated":
            return
        now_ms = _now_ms()
        session.meta.status = status
        session.meta.statusUpdatedAt = now_ms
        session.meta.updatedAt = now_ms
        self._store.write_meta(session.dir, session.meta)

    def _terminate(self, session: Session) -> None:
        """置 terminated 并写 endedAt/procEnd（幂等）。"""
        if session.meta.status == "terminated":
            return
        now_ms = _now_ms()
        session.meta.status = "terminated"
        session.meta.endedAt = now_ms
        session.meta.procEnd = _now_ctime()
        session.meta.statusUpdatedAt = now_ms
        session.meta.updatedAt = now_ms
        self._store.write_meta(session.dir, session.meta)
        logger.info("会话已终止：%s", session.id)
