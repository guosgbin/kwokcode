from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from kwok.server.skill.parser import Skill, parse_skill

__all__ = ["Skill", "SkillLoader", "parse_skill", "SKILL_INDEX_FILENAME"]

SKILL_INDEX_FILENAME = "SKILL.md"


def _discover(step: Path) -> List[Tuple[str, Path]]:
    """扫描一个目录下的 skill 文件：目录 `<name>/SKILL.md` 布局。

    返回 (skill_name, 文件路径) 列表。
    """
    found: List[Tuple[str, Path]] = []
    if not step.is_dir():
        return found
    for child in sorted(step.iterdir()):
        if child.is_dir() and (index := child / SKILL_INDEX_FILENAME).is_file():
            found.append((child.name, index))
    return found


class SkillLoader:
    """skill 三级加载链：项目本地 → 用户全局 → 内建（兜底）。

    支持覆盖语义（本地同名覆盖全局与内建）与短路解析（resolve 命中即止）。
    """

    _BUILTIN_DIR = Path(__file__).resolve().parent / "prebuilt"

    @classmethod
    def _search_paths(cls, cwd: Union[str, Path]) -> List[Path]:
        root = Path(cwd or ".").expanduser()
        return [
            root / ".kwok" / "skills",
            Path("~/.kwok/skills").expanduser(),
            cls._BUILTIN_DIR,
        ]

    def scan_all_skills(self, cwd: Union[str, Path]) -> Dict[str, Skill]:
        """聚合三级目录的全部 skill；后置（更高级）覆盖同名（最终保留本地版本）。"""
        merged: Dict[str, Skill] = {}
        # 先塞内建，再全局，最后本地——后者覆盖前者
        for step in reversed(self._search_paths(cwd)):
            for _, path in _discover(step):
                try:
                    skill = parse_skill(path.read_text(encoding="utf-8"))
                except OSError:
                    continue
                if skill is not None:
                    merged[skill.name] = skill
        return merged

    def list_all_skills(self, cwd: Union[str, Path]) -> List[Dict[str, str]]:
        """暴露给外部的技能列表（弹层/说明用）：name + description。"""
        return [
            {"name": skill.name, "description": skill.description}
            for skill in self.scan_all_skills(cwd).values()
        ]

    def resolve(self, name: str, cwd: Union[str, Path]) -> Optional[Skill]:
        """按名解析 skill：本地 → 全局 → 内建 短路返回，命中即止。"""
        for step in self._search_paths(cwd):
            for cand_name, path in _discover(step):
                if cand_name != name:
                    continue
                try:
                    skill = parse_skill(path.read_text(encoding="utf-8"))
                except OSError:
                    return None
                if skill is not None:
                    return skill
        return None