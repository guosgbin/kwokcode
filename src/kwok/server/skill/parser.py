from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

# frontmatter 顶层字段名
_FIELD_NAME = "name"
_FIELD_DESCRIPTION = "description"
_FIELD_ALLOWED_TOOLS = "allowed_tools"

# 切分 SKILL.md：`---` 之间为 frontmatter，之后为正文
_FRONTMATTER_RE = re.compile(
    r"\A---[ \t]*\r?\n(?P<meta>.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL
)


@dataclass
class Skill:
    """一个 skill = system_prompt 正文 + frontmatter 工具白名单。

    `allowed_tools` 为 None 表示不设限（普通 run）；非空列表表示能力收缩——只向
    模型暴露名单内的工具（匹配不到注册工具的名字被安全忽略）。
    """

    name: str
    description: str = ""
    system_prompt_template: str = ""
    allowed_tools: Optional[List[str]] = None


def _strip_quote(value: str) -> str:
    """去掉单/双引号包裹。"""
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def parse_skill(text: str) -> Skill | None:
    """从 SKILL 文本解析出 Skill：frontmatter 元数据 + 正文作系统提示词。

    frontmatter 必须含 `name:` 字段，缺失说明该文件不是合法 skill，返回 None。
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return None
    meta, body = m.group("meta"), text[m.end():]

    name: str | None = None
    description = ""
    allowed_tools: list[str] | None = None
    lines = meta.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, sep, rest = line.partition(":")
        if not sep:
            continue
        key, rest = key.strip(), rest.strip()
        if key == _FIELD_ALLOWED_TOOLS and not rest:
            # 块序列：`allowed_tools:` 后跟缩进的 `- item`
            allowed_tools = [
                _strip_quote(ln.lstrip()[2:])
                for ln in lines[i + 1:]
                if ln.lstrip().startswith("- ")
            ]
        elif key == _FIELD_NAME and rest:
            name = _strip_quote(rest).strip()
        elif key == _FIELD_DESCRIPTION and rest:
            description = _strip_quote(rest)
    if name is None:
        return None
    return Skill(
        name=name,
        description=description,
        system_prompt_template=body.strip(),
        allowed_tools=allowed_tools or None,
    )