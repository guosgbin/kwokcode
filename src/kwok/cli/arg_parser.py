from __future__ import annotations

import argparse

from kwok.protocol.rpc_model import Method


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kwok", description="KwokCode 命令行客户端")
    sub = parser.add_subparsers(dest="command", required=True)

    prompt = sub.add_parser("prompt", help="直接发起 chat：流式输出大模型回复")
    prompt.add_argument("prompt", type=str, help="提示词")
    prompt.set_defaults(method=Method.PROMPT)

    interactive = sub.add_parser("interactive", help="进入交互式会话模式")
    interactive.set_defaults(method=Method.PROMPT)

    ping = sub.add_parser("ping", help="发送 ping 命令（返回服务端版本/运行信息）")
    ping.set_defaults(method=Method.PING)

    version = sub.add_parser("version", help="打印服务端版本号")
    version.set_defaults(method=Method.VERSION)

    server = sub.add_parser(
        "server", help="管理 kwok-server 守护进程（start / stop / status / restart）"
    )
    server_sub = server.add_subparsers(dest="server_action", required=True)
    server_sub.add_parser("start", help="后台启动 kwok-server 守护进程")
    server_sub.add_parser("stop", help="停止运行中的 kwok-server 守护进程")
    server_sub.add_parser("status", help="查看 kwok-server 运行状态")
    server_sub.add_parser("restart", help="重启 kwok-server 守护进程")
    return parser