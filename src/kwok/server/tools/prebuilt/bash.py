from __future__ import annotations

import subprocess
from typing import Any

from pydantic import BaseModel

from kwok.server.tools.context import cwd_var
from kwok.server.tools.tool import PermissionLevel, ReadWrite, RiskLevel, Tool, ToolCategory, ToolError

_MAX_STDOUT = 32 * 1024
_MAX_STDERR = 8 * 1024


class BashParams(BaseModel):
    """bash 入参：待执行命令 +（可选）单命令超时。"""

    command: str
    timeout: int | None = None


class BashResult(BaseModel):
    """bash 返回值：stdout/stderr/退出码（超时标志）。"""

    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False


class BashTool(Tool):
    """bash：在项目工作目录执行 shell 命令，返回 stdout/stderr/退出码。

    权限：permission_level=ASK，自动接入 PermissionMiddleware 弹窗审批。
    """

    name = "bash"
    description = "在项目工作目录执行 shell 命令，返回 stdout/stderr/退出码。"
    input_model = BashParams
    output_model = BashResult
    permission_level: PermissionLevel = PermissionLevel.ASK
    risk_level: RiskLevel = RiskLevel.HIGH
    category = ToolCategory(business_type="cmd", read_write=ReadWrite.EXEC)
    timeout = 30.0
    all_timeout = 120.0

    def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        cmd = str(args["command"]).strip()
        if not cmd:
            raise ToolError({"error": "bash 失败：命令不能为空"})

        cwd = cwd_var.get() or None
        timeout = args.get("timeout") or self.timeout
        if timeout is not None and timeout <= 0:
            timeout = None

        try:
            proc = subprocess.run(
                cmd,
                cwd=cwd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                start_new_session=True,
            )
        except subprocess.TimeoutExpired:
            return {
                "stdout": "",
                "stderr": (
                    f"命令执行超时（超过 {timeout} 秒），已终止进程组。"
                    "如需更长超时，请通过 timeout 参数指定。"
                ),
                "exit_code": -1,
                "timed_out": True,
            }
        except OSError as exc:
            raise ToolError({"error": f"bash 失败：{exc}"}) from exc

        return {
            "stdout": _truncate(proc.stdout, _MAX_STDOUT),
            "stderr": _truncate(proc.stderr, _MAX_STDERR),
            "exit_code": proc.returncode,
            "timed_out": False,
        }


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...（输出已截断，共 {len(text)} 字节，仅显示前 {limit} 字节）"