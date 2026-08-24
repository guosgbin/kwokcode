from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ValidationError

from kwok.net.requset_context import RequestContext
from kwok.protocol.errors import InvalidParamsError, LlmError
from kwok.protocol.rpc_model import PromptReq, PromptResp, SessionPromptReq
from kwok.server.llm import LlmProvider
from kwok.server.session import SessionManager

logger = logging.getLogger(__name__)


def _parse[T: BaseModel](model_type: type[T], params: Any) -> T:
    """把 RPC params 校验成请求模型；非法参数转 InvalidParamsError。"""
    try:
        return model_type.model_validate({} if params is None else params)
    except ValidationError as exc:
        raise InvalidParamsError(f"无效 prompt 参数: {exc}") from exc


def _require_ctx(ctx: RequestContext | None) -> RequestContext:
    """流式会话必须有 connection_id 和 request_id。"""
    if ctx is None:
        raise LlmError("prompt 需要请求上下文（connection_id）")
    if ctx.request_id is None:
        raise LlmError("prompt 需要请求 id（Notification 不支持流式会话）")
    return ctx


def _require_provider(get_provider: Callable[[], LlmProvider | None]) -> LlmProvider:
    provider = get_provider()
    if provider is None:
        raise LlmError(
            "未配置 LLM 供应商：请在启动 kwok-server 的环境变量中设置 OPENAI_API_KEY"
        )
    return provider


class PromptHandler:
    """one-shot prompt：无会话，临时建一个会话跑完即收。"""

    def __init__(
            self,
            get_provider: Callable[[], LlmProvider | None],
            sessions: SessionManager,
    ) -> None:
        self._get_provider = get_provider
        self._sessions = sessions

    async def __call__(
            self, params: Any, ctx: RequestContext | None = None
    ) -> PromptResp:
        req = _parse(PromptReq, params)
        ctx = _require_ctx(ctx)
        _require_provider(self._get_provider)

        session = self._sessions.create(
            mode="one-shot",
            title=req.prompt[:40],
            cwd=req.cwd,
            owner=ctx.connection_id,
        )
        turn_id = self._sessions.launch_turn(session.id, req.prompt, ctx.connection_id)
        return PromptResp(turn_id=turn_id)


class SessionPromptHandler:
    """交互式会话内 prompt：复用已创建会话，跑一轮 turn。"""

    def __init__(
            self,
            get_provider: Callable[[], LlmProvider | None],
            sessions: SessionManager,
    ) -> None:
        self._get_provider = get_provider
        self._sessions = sessions

    async def __call__(
            self, params: Any, ctx: RequestContext | None = None
    ) -> PromptResp:
        req = _parse(SessionPromptReq, params)
        ctx = _require_ctx(ctx)
        _require_provider(self._get_provider)

        turn_id = self._sessions.launch_turn(req.session_id, req.prompt, ctx.connection_id)
        return PromptResp(turn_id=turn_id)
