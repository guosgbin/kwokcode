from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

from kwok.server.session.meta import SessionMeta

logger = logging.getLogger(__name__)

_META_FILENAME = "session-meta.json"
_SLUG_HYPHEN = "‑"  # U+2011，与 id_generator 时间戳分隔符同字符


class SessionStore:
    """会话文件层：路径解析、slug 编码、原子写 meta、读 meta、扫描会话目录。"""

    def __init__(self, projects_dir: str | Path) -> None:
        self._projects_dir = Path(projects_dir).expanduser()

    @property
    def projects_dir(self) -> Path:
        """存储根目录。"""
        return self._projects_dir

    def _encode_slug(self, cwd: str) -> str:
        """把 cwd 编码为项目 slug：每个 `/`（含前导）替换为 U+2011。"""
        return cwd.rstrip("/").replace("/", _SLUG_HYPHEN)

    def session_dir(self, cwd: str, session_id: str) -> Path:
        """会话目录：<projects_dir>/<slug>/<session_id>/。"""
        return self._projects_dir / self._encode_slug(cwd) / session_id

    def meta_path(self, session_dir: Path) -> Path:
        """会话 meta 文件路径。"""
        return session_dir / _META_FILENAME

    def write_meta(self, session_dir: Path, meta: SessionMeta) -> None:
        """原子写 meta：同目录临时文件 + os.replace。"""
        session_dir.mkdir(parents=True, exist_ok=True)
        target = self.meta_path(session_dir)
        fd, tmp_path = tempfile.mkstemp(dir=session_dir, prefix=".meta-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(meta.model_dump_json(indent=2) + "\n")
            os.replace(tmp_path, target)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def read_meta(self, session_dir: Path) -> SessionMeta | None:
        """读会话 meta；文件缺失或解析失败返回 None。"""
        path = self.meta_path(session_dir)
        if not path.is_file():
            return None
        try:
            return SessionMeta.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            logger.warning("会话 meta 无法解析，跳过：%s", path)
            return None

    def list_session_dirs(self, cwd: str) -> list[Path]:
        """列出项目下全部会话目录（按目录名排序）。"""
        project_dir = self._projects_dir / self._encode_slug(cwd)
        if not project_dir.is_dir():
            return []
        return sorted((p for p in project_dir.iterdir() if p.is_dir()), key=lambda p: p.name)
