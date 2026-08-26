"""MCP 配置加载：全局 ~/.kwok/mcp.json + 项目本地 .kwok/mcp.json 双层叠加、严格校验。

对象键级合并（项目本地覆盖全局同名 server，仅存在一方的保留），逐项校验
transport / command / url（FR-002），非法项拒绝并给出可读错误，合法项照常
展平为 ``McpConfig.servers`` 列表（FR-001）。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from kwok.config import McpConfig, McpServerConfig

logger = logging.getLogger(__name__)

_GLOBAL_MCP_CONFIG = "~/.kwok/mcp.json"
_PROJECT_MCP_CONFIG = ".kwok/mcp.json"


def load_mcp_config() -> McpConfig:
    """读双层 mcp.json，对象键级合并后逐项校验，返回合法 server 列表。

    全局为基底、项目本地覆盖同名 server；单文件缺失/JSON 错误静默跳过；
    非法项 log 可读错误并拒绝，不影响合法项。
    """
    merged: dict[str, dict[str, Any]] = {}
    for path in (_global_mcp_config_path(), _project_mcp_config_path()):
        servers = _read_servers(path)
        if servers is None:
            continue
        merged.update(servers)  # 后加载者覆盖同名（项目本地后加载 → 覆盖全局）

    valid: list[McpServerConfig] = []
    for name, raw in merged.items():
        cfg = _parse_server(name, raw)
        if cfg is not None:
            valid.append(cfg)
    return McpConfig(servers=valid)


def _global_mcp_config_path() -> Path:
    return Path(_GLOBAL_MCP_CONFIG).expanduser()


def _project_mcp_config_path() -> Path:
    return Path.cwd() / _PROJECT_MCP_CONFIG


def _read_servers(path: Path) -> dict[str, dict[str, Any]] | None:
    """读单个文件的 mcpServers 对象；缺文件/解析失败/非对象均 log 并返回 None。"""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("MCP 配置读取失败 %s：%s", path, exc)
        return None
    if not isinstance(data, dict):
        logger.warning("MCP 配置 %s 顶层必须是 JSON 对象", path)
        return None
    mcp_servers = data.get("mcpServers", {})
    if not isinstance(mcp_servers, dict):
        logger.warning("MCP 配置 %s 的 mcpServers 必须是对象（键为 server 名）", path)
        return None
    result: dict[str, dict[str, Any]] = {}
    for name, raw in mcp_servers.items():
        if isinstance(raw, dict):
            result[str(name)] = raw
        else:
            logger.warning("MCP server %r 配置必须是对象，已忽略", name)
    return result


def _parse_server(name: str, raw: dict[str, Any]) -> McpServerConfig | None:
    """校验单个 server 配置（FR-002）；非法返回 None 并 log 可读错误。"""
    transport = raw.get("transport", "stdio")
    if transport not in ("stdio", "http"):
        logger.warning(
            "MCP server %r 非法：transport 必须是 stdio 或 http（当前 %r）", name, transport
        )
        return None

    command = raw.get("command")
    url = raw.get("url")
    if transport == "stdio":
        if not isinstance(command, str) or not command.strip():
            logger.warning("MCP server %r 非法：stdio 必须提供非空 command", name)
            return None
    else:
        if not isinstance(url, str) or not url.strip():
            logger.warning("MCP server %r 非法：http 必须提供非空 url", name)
            return None

    args = _str_list(raw.get("args"))
    if args is None:
        logger.warning("MCP server %r 非法：args 必须是字符串数组", name)
        return None
    env = raw.get("env")
    if env is not None and not isinstance(env, dict):
        logger.warning("MCP server %r 非法：env 必须是对象", name)
        return None
    cwd = raw.get("cwd")
    if cwd is not None and not isinstance(cwd, str):
        logger.warning("MCP server %r 非法：cwd 必须是字符串", name)
        return None

    return McpServerConfig(
        name=name,
        transport=transport,
        command=command if isinstance(command, str) else None,
        args=args,
        env=env,
        cwd=cwd,
        url=url if isinstance(url, str) else None,
    )


def _str_list(value: object) -> list[str] | None:
    """可选字符串数组；None → []，非字符串数组 → None（非法）。"""
    if value is None:
        return []
    if isinstance(value, list) and all(isinstance(x, str) for x in value):
        return [str(x) for x in value]
    return None
