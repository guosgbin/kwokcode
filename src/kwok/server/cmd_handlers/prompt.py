from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from kwok.net.requset_context import RequestContext
from kwok.protocol.errors import LlmError
from kwok.protocol.rpc_model import PromptReq, PromptResp
from kwok.server.event.manager import EventBusManager
from kwok.server.llm import LlmProvider
from kwok.server.llm.loop import run
from kwok.server.tools import read_file_tool
from kwok.util.id_generator import gen_turn_id

logger = logging.getLogger(__name__)


class PromptHandler:

    def __init__(
            self, bus: EventBusManager, get_provider: Callable[[], LlmProvider | None]
    ) -> None:
        self._bus = bus
        self._get_provider = get_provider
        self._tasks: set[asyncio.Task[None]] = set()

    async def __call__(
            self, params: Any, ctx: RequestContext | None = None
    ) -> PromptResp:
        req = PromptReq.model_validate({} if params is None else params)
        provider = self._get_provider()
        if provider is None:
            raise LlmError(
                "未配置 LLM 供应商：请在启动 kwok-server 的环境变量中设置 OPENAI_API_KEY"
            )
        if ctx is None:
            raise LlmError("prompt 需要请求上下文（connection_id）")
        if ctx.request_id is None:
            raise LlmError("prompt 需要请求 id（Notification 不支持流式会话）")
        turn_id = gen_turn_id()
        task = asyncio.create_task(
            run(
                self._bus, provider, req.prompt, turn_id,
                tools=[read_file_tool.schema],
            )
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return PromptResp(turn_id=turn_id)