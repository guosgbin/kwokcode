from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

from kwok.server.session.meta import SessionMeta

logger = logging.getLogger(__name__)

_META_FILENAME = "session-meta.json"
_MEMORY_DIRNAME = "memory"
_INDEX_FILENAME = "MEMORY.md"
_SLUG_HYPHEN = "‑"  # U+2011，与 id_generator 时间戳分隔符同字符


def encode_cwd_slug(cwd: str) -> str:
    """把 cwd 编码为项目 slug：每个 `/`（含前导）替换为 U+2011。"""
    return cwd.rstrip("/").replace("/", _SLUG_HYPHEN)


def _slug_name(name: str) -> str:
    """记忆名 slug 化：去空白、折叠路径分隔符、吞掉 `..`，防目录逃逸。"""
    cleaned = name.strip().replace("/", "-").replace("\\", "-")
    return cleaned.replace("..", "_")


def _default_summary(content: str) -> str:
    """缺省 summary：取 content 首个非空行。"""
    for line in content.splitlines():
        if line.strip():
            return line.strip()
    return ""


def _index_text(summary: str) -> str:
    """summary → 索引行标题文本：转义 [ ] 防止破坏 markdown 链接。"""
    return summary.replace("[", r"\[").replace("]", r"\]").strip()


class SessionStore:
    """会话与项目记忆文件层：路径解析、slug 编码、原子写 meta、读 meta、扫描会话目录。"""

    def __init__(self, projects_dir: str | Path) -> None:
        self._projects_dir = Path(projects_dir).expanduser()

    @property
    def projects_dir(self) -> Path:
        """存储根目录。"""
        return self._projects_dir

    def session_dir(self, cwd: str, session_id: str) -> Path:
        """会话目录：<projects_dir>/<slug>/<session_id>/。"""
        return self._projects_dir / encode_cwd_slug(cwd) / session_id

    def memory_dir(self, cwd: str) -> Path:
        """项目记忆目录：<projects_dir>/<slug>/memory/。"""
        return self._projects_dir / encode_cwd_slug(cwd) / _MEMORY_DIRNAME

    def memory_path(self, cwd: str, name: str) -> Path:
        """指定记忆名的文件路径：<memory_dir>/<slug>.md。"""
        return self.memory_dir(cwd) / f"{_slug_name(name)}.md"

    def write_memory(
        self,
        cwd: str,
        name: str,
        content: str,
        *,
        summary: str | None = None,
    ) -> Path:
        """写入/覆盖一条项目记忆：原子写 <name>.md，并在 MEMORY.md 里 upsert 索引行。"""
        target = self.memory_path(cwd, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=target.parent, prefix=".mem-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
                if not content.endswith("\n"):
                    handle.write("\n")
            os.replace(tmp_path, target)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        self._upsert_memory_index(cwd, target.name, summary or _default_summary(content))
        return target

    def _upsert_memory_index(self, cwd: str, filename: str, summary: str) -> None:
        """在 MEMORY.md 里按文件名 upsert 一行 `- [<summary>](<filename>)`。"""
        index = self.memory_dir(cwd) / _INDEX_FILENAME
        lines: list[str] = []
        if index.is_file():
            try:
                lines = index.read_text(encoding="utf-8").splitlines()
            except OSError:
                lines = []
        marker = f"]({filename})"
        lines = [ln for ln in lines if marker not in ln]
        lines.append(f"- [{_index_text(summary)}]({filename})")
        index.write_text("\n".join(lines) + "\n", encoding="utf-8")

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