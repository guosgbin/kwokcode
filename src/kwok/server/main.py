from __future__ import annotations

import asyncio
import logging

from kwok.config import get_config
from kwok.server.app import KwokApp

logger = logging.getLogger(__name__)


def main() -> None:
    cfg = get_config()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    try:
        asyncio.run(KwokApp().start())
    except KeyboardInterrupt:
        logger.info("kwok-server 收到退出信号，正在关闭")


if __name__ == "__main__":
    main()
