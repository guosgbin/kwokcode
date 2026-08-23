from enum import IntEnum


class ErrorCode(IntEnum):
    EVENT_LLM_INSUFFICIENT_BALANCE = 4000

    @property
    def default_msg(self) -> str:
        _map = {
            ErrorCode.EVENT_LLM_INSUFFICIENT_BALANCE: "余额不足",
        }
        return _map.get(self, "未知错误")
