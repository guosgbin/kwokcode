"""kwok 统一入口：无参数默认进 TUI，带子命令走 CLI。

服务端 daemon 不经此入口暴露（由 `kwok server start` 内部经
`python -m kwok.server` 拉起），故不提供 kwok-server 命令。
"""
from __future__ import annotations

import sys


def main() -> None:
    # 无任何参数 → 默认进 TUI（KwokCode 主导体验）
    if len(sys.argv) == 1:
        _enter_tui()
        return
    _run_cli()


def _enter_tui() -> None:
    from kwok.tui.main import main as tui_main

    tui_main()


def _run_cli() -> None:
    from kwok.cli.main import main as cli_main

    cli_main()


if __name__ == "__main__":
    main()