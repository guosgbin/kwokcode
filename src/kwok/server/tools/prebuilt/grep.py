from __future__ import annotations

import subprocess
from typing import Any

from pydantic import BaseModel

from kwok.server.tools.context import cwd_var
from kwok.server.tools.tool import PermissionLevel, ReadWrite, RiskLevel, Tool, ToolCategory, ToolError

_MAX_GREP_OUTPUT = 32 * 1024
_GREP_TIMEOUT = 20.0


class GrepParams(BaseModel):
    """grep 入参：正则模式 + 搜索范围/过滤/输出模式/分页。"""

    pattern: str
    path: str | None = None
    glob: str | None = None
    type: str | None = None
    output_mode: str = "files_with_matches"
    multiline: bool = False
    head_limit: int | None = None
    offset: int | None = None


class GrepResult(BaseModel):
    """grep 返回值：rg 输出 + 模式 + 可选总计。"""

    output: str
    mode: str
    total_matches: int | None = None


class GrepTool(Tool):
    """grep：基于 ripgrep 在文件内容中搜索正则模式。

    权限：permission_level=ASK，自动接入 PermissionMiddleware 弹窗审批。
    """

    name = "grep"
    description = (
        "基于 ripgrep 在文件内容中搜索正则模式。"
        "默认返回匹配文件路径，可切换为 content（匹配行+行号）或 count（匹配计数）。"
    )
    input_model = GrepParams
    output_model = GrepResult
    permission_level: PermissionLevel = PermissionLevel.ASK
    risk_level: RiskLevel = RiskLevel.READONLY
    category = ToolCategory(business_type="file", read_write=ReadWrite.READ)
    timeout = _GREP_TIMEOUT
    all_timeout = _GREP_TIMEOUT

    def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        pattern = str(args["pattern"]).strip()
        if not pattern:
            raise ToolError({"error": "grep 失败：pattern 不能为空"})

        cwd = cwd_var.get() or "."
        cmd = self._build_rg_cmd(args, cwd)

        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=_GREP_TIMEOUT, cwd=cwd,
            )
        except FileNotFoundError:
            raise ToolError({"error": "ripgrep 未安装，请先安装 rg"}) from None
        except subprocess.TimeoutExpired:
            raise ToolError({
                "error": f"grep 超时（超过 {_GREP_TIMEOUT} 秒），请缩小搜索范围或增加 head_limit"
            }) from None

        mode = args.get("output_mode", "files_with_matches")

        if proc.returncode == 2:
            err = self._handle_rg_error(proc.stderr)
            return {"output": err["output"], "mode": err["mode"], "total_matches": err.get("total_matches")}

        output = proc.stdout

        if args.get("head_limit") is not None or args.get("offset") is not None:
            output = self._apply_pagination(output, mode, args)

        if len(output.encode("utf-8")) > _MAX_GREP_OUTPUT:
            output = output[:_MAX_GREP_OUTPUT] + "\n…（输出已截断）"

        return {"output": output, "mode": mode}

    def _build_rg_cmd(self, args: dict[str, Any], cwd: str) -> list[str]:
        cmd = ["rg", "--color=never", "--no-heading"]

        mode = args.get("output_mode", "files_with_matches")
        if mode == "files_with_matches":
            cmd.append("--files-with-matches")
        elif mode == "content":
            cmd.append("--line-number")
        elif mode == "count":
            cmd.append("--count")

        if args.get("glob"):
            cmd.extend(["--glob", args["glob"]])
        if args.get("type"):
            cmd.extend(["--type", args["type"]])
        if args.get("multiline"):
            cmd.append("--multiline")

        path = args.get("path") or cwd
        cmd.extend([args["pattern"], path])
        return cmd

    def _handle_rg_error(self, stderr: str) -> dict[str, Any]:
        stderr = stderr.strip()
        if "regex parse error" in stderr.lower():
            raise ToolError({"error": f"正则解析失败：{stderr}"})
        if "no files found" in stderr.lower():
            return {"output": "", "mode": "files_with_matches", "total_matches": 0}
        raise ToolError({"error": f"grep 失败：{stderr}"})

    def _apply_pagination(self, output: str, mode: str, args: dict[str, Any]) -> str:
        lines = output.splitlines()
        offset = args.get("offset") or 0
        head_limit = args.get("head_limit")

        total_line = None
        if mode == "count" and lines and "matches" in lines[-1]:
            total_line = lines[-1]
            lines = lines[:-1]

        if offset:
            lines = lines[offset:]
        if head_limit is not None:
            lines = lines[:head_limit]

        if total_line:
            lines.append(total_line)

        return "\n".join(lines)
