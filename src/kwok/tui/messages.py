from __future__ import annotations

from textual.message import Message

from kwok.protocol.events import BaseEvent


class EventMessage(Message):
    """承载任意 server 事件，从消费 worker 投递到 App 主线程渲染。"""

    def __init__(self, event: BaseEvent) -> None:
        self.event = event
        super().__init__()


class SubmitPrompt(Message):
    """用户提交 prompt（或斜杠命令），由 InputPanel 发出。"""

    def __init__(self, prompt: str) -> None:
        self.prompt = prompt
        super().__init__()


class ConnectResult(Message):
    """连接/会话建立结果：成功携带 session_id，失败携带可读错误。"""

    def __init__(self, ok: bool, session_id: str = "", error: str = "") -> None:
        self.ok = ok
        self.session_id = session_id
        self.error = error
        super().__init__()


class ConnectionLost(Message):
    """连接中断通知。"""

    def __init__(self, error: str) -> None:
        self.error = error
        super().__init__()
