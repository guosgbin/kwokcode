from __future__ import annotations

from contextvars import ContextVar

# 当前事件发布所属的连接 id。
# set：SocketServer._handle_client 连接建立时；传播：asyncio.create_task 拷贝
# 当前 task 的 context，因此该连接的全部 RPC 请求任务及其派生的 turn / 子 agent
# 任务都继承此值。
# 消费：ClientEventPush.publish 按此值把会话事件只投递给该连接的 sender，
# 实现跨会话隔离（一个连接的事件不再广播给其它连接）。
# 连接上下文之外（如 serve_forever 发布 server.status）为 None。
connection_id_var: ContextVar[str | None] = ContextVar("connection_id", default=None)
