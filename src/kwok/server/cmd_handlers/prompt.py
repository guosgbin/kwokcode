from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from kwok.net.requset_context import RequestContext
from kwok.protocol.errors import InvalidParamsError, LlmError
from kwok.protocol.rpc_model import PromptReq, PromptResp
from kwok.server.event.manager import EventBusManager
from kwok.server.llm import LlmProvider
from kwok.server.session import SessionManager
from kwok.util.id_generator import gen_turn_id

logger = logging.getLogger(__name__)


class PromptHandler:

    def __init__(
            self,
            bus: EventBusManager,
            get_provider: Callable[[], LlmProvider | None],
            sessions: SessionManager,
    ) -> None:
        self._bus = bus
        self._get_provider = get_provider
        self._sessions = sessions
        self._tasks: set[asyncio.Task[None]] = set()

    async def __call__(
            self, params: Any, ctx: RequestContext | None = None
    ) -> PromptResp:
        try:
            req = PromptReq.model_validate({} if params is None else params)
        except ValidationError as exc:
            raise InvalidParamsError(f"无效 prompt 参数: {exc}") from exc
        if ctx is None:
            raise LlmError("prompt 需要请求上下文（connection_id）")
        if ctx.request_id is None:
            raise LlmError("prompt 需要请求 id（Notification 不支持流式会话）")
        provider = self._get_provider()
        if provider is None:
            raise LlmError(
                "未配置 LLM 供应商：请在启动 kwok-server 的环境变量中设置 OPENAI_API_KEY"
            )

        if req.session_id is None:
            if not req.cwd or not req.cwd.strip():
                raise InvalidParamsError("one-shot prompt 需要 cwd（会话工作目录）")
            session = self._sessions.create(
                mode="one-shot",
                title=req.prompt[:40],
                cwd=req.cwd,
                owner=ctx.connection_id,
            )
            session_id = session.id
        else:
            session_id = req.session_id
        self._sessions.begin_turn(session_id, ctx.connection_id)

        turn_id = gen_turn_id()
        task = asyncio.create_task(
            self._sessions.send_message(session_id, req.prompt, turn_id)
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return PromptResp(turn_id=turn_id)
