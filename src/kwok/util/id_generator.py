import uuid
from datetime import datetime
from zoneinfo import ZoneInfo


def gen_request_id() -> str:
    time_part = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d‑%H%M%S")
    uuid_short = str(uuid.uuid4())[:6]
    return f"{time_part}-{uuid_short}"


def gen_turn_id() -> str:
    return gen_request_id()
