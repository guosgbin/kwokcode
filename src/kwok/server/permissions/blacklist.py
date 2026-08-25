from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kwok.server.llm.model import ToolCall


@dataclass(frozen=True)
class BlockReason:
    """黑名单命中信息：被拦工具 + 原因（供 LLM 提示）。"""

    tool_name: str
    reason: str


# 危险目标集合：删除目标指向根/家目录/工作区整删，视为高危。
# 判定只看 token 本身，如 '/'、'~'、'/*'、'.' 等（不解析通配展开）。
_DANGEROUS_TARGETS = {
    "/",
    "//",
    "/*",
    "/.",
    "~",
    "~/*",
    ".",
    "./*",
}


def check_blacklist(call: ToolCall) -> BlockReason | None:
    """按工具分发到黑名单匹配器；未命中返回 None。"""
    if call.name == "bash":
        return _match_bash(_command_args(call))
    return None


def _command_args(call: ToolCall) -> str:
    args: Any = call.validated_args
    if isinstance(args, dict) and isinstance(args.get("command"), str):
        return args["command"]
    return call.arguments or ""


def _match_bash(cmd: str) -> BlockReason | None:
    try:
        tokens = shlex.split(cmd)
    except ValueError:
        tokens = cmd.split()
    if not tokens:
        return None

    base = tokens[0]

    # rm 的递归/强制删除 + 危险目标
    if base == "rm" and {"-rf", "-fr", "-r", "-f", "-fr"} & set(tokens):
        target = _dangerous_rm_target(tokens)
        if target is not None:
            return BlockReason(
                tool_name="bash",
                reason=(
                    f"命令 `{cmd}` 会对危险路径 `{target}` 执行强制递归删除，"
                    f"可能导致根目录/家目录/工作区不可恢复，已强制拒绝。"
                ),
            )

    # mkfs / mkfs.* 格式化文件系统
    if base == "mkfs" or base.startswith("mkfs."):
        return BlockReason(
            tool_name="bash",
            reason=(
                f"命令 `{cmd}` 调用 `{base}` 格式化文件系统，"
                f"会导致磁盘数据不可恢复，已强制拒绝。"
            ),
        )

    # 直接往块设备写
    if base == "dd":
        of = _option_value(tokens, "of")
        if of is not None and _is_block_device(of):
            return BlockReason(
                tool_name="bash",
                reason=(
                    f"命令 `{cmd}` 通过 dd 向块设备 `{of}` 写入，"
                    f"可能导致磁盘数据不可恢复，已强制拒绝。"
                ),
            )

    return None


def _dangerous_rm_target(tokens: list[str]) -> str | None:
    """在 rm 的 -[rRf] 组合下，目标为危险路径时返回该目标。"""
    for t in tokens[1:]:
        if t.startswith("-"):
            continue
        # 规整：剥掉结尾斜杠再判
        normalized = t.rstrip("/") or "/"
        if normalized in _DANGEROUS_TARGETS:
            return t
    return None


def _option_value(tokens: list[str], want: str) -> str | None:
    for i, t in enumerate(tokens):
        if t.startswith(want + "="):
            return t.split("=", 1)[1]
        if t == want and i + 1 < len(tokens):
            return tokens[i + 1]
    return None


def _is_block_device(target: str) -> bool:
    return target.startswith("/dev/")