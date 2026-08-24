import logging
import logging.handlers
import sys
from pathlib import Path

ROTATE_MAX_BYTES = 10 * 1024 * 1024
ROTATE_BACKUP_COUNT = 5

LOG_FMT = (
    "%(asctime)s %(levelname)-8s %(name)s:%(funcName)s:%(lineno)d %(message)s"
)
DATE_FMT = "%Y-%m-%d %H:%M:%S"


def setup_logging(
        level: str = "INFO",
        log_file: str | None = None,
        console: bool = True,
) -> None:
    root_logger = logging.getLogger()

    root_logger.handlers.clear()
    root_logger.setLevel(level)

    formatter = logging.Formatter(fmt=LOG_FMT, datefmt=DATE_FMT)

    if console:
        console_handler = logging.StreamHandler(stream=sys.stderr)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    if log_file is not None:
        log_path = Path(log_file).expanduser()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            filename=log_path,
            maxBytes=ROTATE_MAX_BYTES,
            backupCount=ROTATE_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("kwok").setLevel(level)
