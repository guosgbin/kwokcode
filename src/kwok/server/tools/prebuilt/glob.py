from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from kwok.server.tools.context import cwd_var
from kwok.server.tools.tool import PermissionLevel, ReadWrite, RiskLevel, Tool, ToolCategory, ToolError

_GLOB_LIMIT = 100


class GlobParams(BaseModel):
    """glob 入参：文件名模式 + 搜索根目录 + 是否尊重 gitignore。"""

    pattern: str
    path: str | None = None
    respect_gitignore: bool = False


class GlobResult(BaseModel):
    """glob 返回值：匹配文件列表 + 总数 + 是否截断。"""

    files: list[str]
    total: int
    truncated: bool


def _expand_braces(pattern: str) -> list[str]:
    """*.{json,yaml} → ['*.json', '*.yaml']；无 brace 时原样返回。"""

    m = re.search(r"\{([^}]+)\}", pattern)
    if not m:
        return [pattern]
    prefix, suffix = pattern[: m.start()], pattern[m.end() :]
    return [f"{prefix}{opt}{suffix}" for opt in m.group(1).split(",")]


def _load_gitignore_spec(root: Path) -> Any | None:
    """从 root 读取 .gitignore 并返回 pathspec 实例；无文件返回 None。"""

    gitignore = root / ".gitignore"
    if not gitignore.is_file():
        return None
    try:
        import pathspec

        lines = gitignore.read_text(encoding="utf-8", errors="replace").splitlines()
        return pathspec.PathSpec.from_lines("gitwildmatch", lines)
    except ImportError:
        raise ToolError({
            "error": (
                "respect_gitignore=true 需要 pathspec 库，请先安装：pip install pathspec"
            )
        }) from None


class GlobTool(Tool):
    """glob：按文件名模式查找文件，支持 ** 递归和 {a,b} brace expansion。

    默认不尊重 .gitignore（和 Claude Code 一致）；传 respect_gitignore=true 可过滤。
    """

    name = "glob"
    description = (
        "按文件名模式查找文件。支持 ** 递归目录匹配和 {a,b} brace expansion。"
        "默认不尊重 .gitignore；设置 respect_gitignore=true 可过滤被忽略的文件。"
        "结果按修改时间降序，最多返回 25 个文件。"
    )
    input_model = GlobParams
    output_model = GlobResult
    permission_level: PermissionLevel = PermissionLevel.ALLOW
    risk_level: RiskLevel = RiskLevel.READONLY
    category = ToolCategory(business_type="file", read_write=ReadWrite.READ)

    def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        pattern = str(args["pattern"])
        if "\x00" in pattern:
            raise ToolError({"error": "pattern 包含空字节，请删除后重试"})

        cwd = cwd_var.get() or "."
        raw_path = args.get("path") or cwd
        root = Path(raw_path).resolve()
        if not root.is_dir():
            raise ToolError({"error": f"搜索根目录不存在：{root}"})

        respect_gitignore = bool(args.get("respect_gitignore", False))
        spec = _load_gitignore_spec(root) if respect_gitignore else None

        patterns = _expand_braces(pattern)
        matches: set[Path] = set()
        for pat in patterns:
            try:
                for p in root.glob(pat):
                    if p.is_file():
                        matches.add(p)
            except OSError:
                continue

        if spec is not None:
            matches = {p for p in matches if not spec.match_file(p.relative_to(root))}

        files = sorted(matches, key=lambda p: p.stat().st_mtime, reverse=True)
        total = len(files)
        truncated = total > _GLOB_LIMIT
        files = files[:_GLOB_LIMIT]

        result = [str(p.relative_to(root)) for p in files]
        return {"files": result, "total": total, "truncated": truncated}
