from __future__ import annotations

import sys

from kwok.config import init_config
from kwok.tui.app import KwokTuiApp


def main() -> None:
    """kwok-tui 入口：初始化配置快照后启动 textual App。"""
    init_config()
    app = KwokTuiApp()
    sys.exit(app.run())


if __name__ == "__main__":
    main()

