from __future__ import annotations

from pathlib import Path

from kwok.server.subagent.parser import AgentRole, parse_role

__all__ = ["AgentLoader", "AgentRole", "parse_role"]


class AgentLoader:
    """角色三级加载链：项目本地 → 用户全局 → 内建（兜底），短路解析命中即止。

    角色目录布局：`<dir>/<name>.md`。三级目录：
        1. <cwd>/.kwok/subagent/      （项目本地）
        2. ~/.kwok/subagent/          （用户全局）
        3. 包内 builtin/              （内建兜底）
    """

    _BUILTIN_DIR = Path(__file__).resolve().parent / "builtin"

    @classmethod
    def _search_paths(cls, cwd: str | Path) -> list[Path]:
        root = Path(cwd or ".").expanduser()
        return [
            root / ".kwok" / "subagent",
            Path("~/.kwok/subagent").expanduser(),
            cls._BUILTIN_DIR,
        ]

    def resolve(self, name: str, cwd: str | Path) -> AgentRole | None:
        """按名解析角色：本地 → 全局 → 内建短路返回，命中即止；三处皆无返回 None。"""
        for step in self._search_paths(cwd):
            path = step / f"{name}.md"
            if not path.is_file():
                continue
            try:
                role = parse_role(path.read_text(encoding="utf-8"))
            except OSError:
                return None
            if role is not None:
                return role
        return None
