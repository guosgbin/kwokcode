from __future__ import annotations

import re
from dataclasses import dataclass

# 切分角色 md：`---` 之间为 frontmatter，之后为正文（子 agent 系统提示词）
_FRONTMATTER_RE = re.compile(
    r"\A---[ \t]*\r?\n(?P<meta>.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL
)


@dataclass(frozen=True)
class AgentRole:
    """一个角色 = md 四字段 + 提示词正文。

    - ``tools``: 工具白名单（子 agent 注册表物理限制）；空 = 空白名单（fail-closed）。
    - ``model``: 子 agent 模型；None = 继承父 agent 模型。
    - ``system_prompt``: 角色正文，作为子 agent 系统提示词（冷启动，不含父记忆）。
    """

    name: str
    description: str = ""
    tools: tuple[str, ...] = ()
    model: str | None = None
    system_prompt: str = ""


def _strip_quote(value: str) -> str:
    """去掉单/双引号包裹。"""
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def parse_role(text: str) -> AgentRole | None:
    """从角色 md 文本解析出 AgentRole：frontmatter 四字段 + 正文。

    frontmatter 必须含 ``name:``；缺失说明不是合法角色，返回 None。
    tools 支持单行逗号分隔（``tools: read, glob``）或块列表（``tools:`` 后缩进 ``- item``）。
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return None
    meta, body = m.group("meta"), text[m.end():]

    name: str | None = None
    description = ""
    tools: tuple[str, ...] = ()
    model: str | None = None
    lines = meta.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, sep, rest = line.partition(":")
        if not sep:
            continue
        key, rest = key.strip(), rest.strip()
        if key == "tools" and rest:
            # 单行逗号分隔：`tools: read, glob, grep`
            tools = tuple(t.strip() for t in rest.split(",") if t.strip())
        elif key == "tools" and not rest:
            # 块列表：`tools:` 后跟缩进的 `- item`
            tools = tuple(
                _strip_quote(ln.lstrip()[2:])
                for ln in lines[i + 1:]
                if ln.lstrip().startswith("- ")
            )
        elif key == "name" and rest:
            name = _strip_quote(rest).strip()
        elif key == "description" and rest:
            description = _strip_quote(rest)
        elif key == "model" and rest:
            model = _strip_quote(rest).strip() or None
    if name is None:
        return None
    return AgentRole(
        name=name,
        description=description,
        tools=tools,
        model=model,
        system_prompt=body.strip(),
    )
