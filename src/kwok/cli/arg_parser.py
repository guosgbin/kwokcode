from __future__ import annotations

import argparse
from collections.abc import Iterable

from kwok.config import get_config
from kwok.protocol.enums import Method


class _KwokParser(argparse.ArgumentParser):

    def parse_args(
            self, args: Iterable[str] | None = None, namespace: argparse.Namespace | None = None
    ) -> argparse.Namespace:
        ns = super().parse_args(args, namespace)
        self._validate(ns)
        return ns

    def _validate(self, ns: argparse.Namespace) -> None:
        prompt_raw = getattr(ns, "prompt", None)
        if prompt_raw is not None:
            if getattr(ns, "command", None) is not None:
                self.error("`-p/--prompt` 与子命令互斥，请二选一")
            stripped = prompt_raw.strip()
            if not stripped:
                self.error("提示词不能为空")
            max_length = get_config().llm.prompt_max_length
            if len(stripped) > max_length:
                self.error(f"提示词过长（>{max_length} 字符）")
            ns.prompt = stripped
            ns.method = Method.CHAT
            return
        if getattr(ns, "command", None) is None:
            self.error("必须提供子命令或 -p/--prompt")


def build_parser() -> argparse.ArgumentParser:
    parser = _KwokParser(prog="kwok-cli", description="KwokCode 命令行客户端")
    parser.add_argument(
        "-p", "--prompt", type=str, default=None, help="直接发起 chat：流式输出大模型回复"
    )
    sub = parser.add_subparsers(dest="command")

    ping = sub.add_parser("ping", help="发送 ping 命令（返回服务端版本/运行信息）")
    ping.set_defaults(method=Method.PING)

    version = sub.add_parser("version", help="打印服务端版本号")
    version.set_defaults(method=Method.VERSION)

    event_types = sub.add_parser(
        "event-types", help="列出服务端已注册的事件类型（发布订阅主题，供 TUI 参考）"
    )
    event_types.set_defaults(method=Method.EVENT_TYPES)

    server = sub.add_parser(
        "server", help="管理 kwok-server 守护进程（start / stop / status / restart）"
    )
    server_sub = server.add_subparsers(dest="server_action", required=True)
    server_sub.add_parser("start", help="后台启动 kwok-server 守护进程")
    server_sub.add_parser("stop", help="停止运行中的 kwok-server 守护进程")
    server_sub.add_parser("status", help="查看 kwok-server 运行状态")
    server_sub.add_parser("restart", help="重启 kwok-server 守护进程")
    return parser
