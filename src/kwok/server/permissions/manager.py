from __future__ import annotations

import asyncio
import logging
from typing import Any

from kwok.protocol.enums import PermissionDecision
from kwok.protocol.events import (
    PermissionDeniedEvent,
    PermissionGrantedEvent,
    PermissionRequestedEvent,
)
from kwok.server.event import EventBusManager, get_bus
from kwok.server.llm.model import ToolCall
from kwok.server.permissions.blacklist import check_blacklist
from kwok.server.permissions.cache import SessionDecisionCache
from kwok.server.permissions.errors import (
    PermissionBlacklistError,
    PermissionDeniedError,
    PermissionTimeoutError,
)
from kwok.server.permissions.models import PermissionOutcome, PermissionResult
from kwok.server.tools.tool import PermissionLevel

logger = logging.getLogger(__name__)


class PermissionManager:
    """工具权限审批核心：预决 → 本 session 缓存 → 挂起审批（asyncio.Future 解耦）。

    以 tool_use_id 隔离并发审批；会话级决策仅本 session 内存缓存，不落盘（FR-013）；
    决策字符串全链路透传（protocol.enums.PermissionDecision 为唯一事实源）。
    """

    def __init__(self, *, bus: EventBusManager, timeout_s: float) -> None:
        self._bus = bus
        self._timeout_s = timeout_s
        # tool_use_id → (Future, session_id)；Future 解耦审批等待与 respond 回传
        self._pending: dict[str, tuple[asyncio.Future[PermissionDecision], str]] = {}
        self._cache = SessionDecisionCache()

    async def check(self, call: ToolCall, session_id: str) -> PermissionOutcome:
        """检查权限：黑名单强拒 → 元数据预决 → 缓存命中 → 挂起审批并等待决策（阻塞式）。"""
        level = self._level(call)

        # 高危黑名单：第一优先强拒，不弹窗、不走缓存（防 user allow 绕过）
        block = check_blacklist(call)
        if block is not None:
            return await self._decide(
                PermissionDecision.AUTO_DENY,
                call,
                session_id,
                error=PermissionBlacklistError(block.reason),
            )

        if level is PermissionLevel.ALLOW:
            return await self._decide(PermissionDecision.AUTO_ALLOW, call, session_id)
        if level is PermissionLevel.DENY:
            return await self._decide(PermissionDecision.AUTO_DENY, call, session_id)

        cached = self._cache.get(session_id, call.name)
        if cached is not None:
            return await self._decide(cached, call, session_id)

        # ask 工具：挂起审批，发布 requested，等待 respond / 超时 / 断连
        future: asyncio.Future[PermissionDecision] = asyncio.get_running_loop().create_future()
        self._pending[call.id] = (future, session_id)
        try:
            await self._bus.publish(
                PermissionRequestedEvent(
                    tool_use_id=call.id,
                    session_id=session_id,
                    tool_name=call.name,
                    param_preview=self._preview(call),
                    timeout_s=self._timeout_s if self._timeout_s > 0 else None,
                )
            )
            try:
                decision = await self._wait(future)
            except TimeoutError:
                decision = PermissionDecision.TIMEOUT
        except asyncio.CancelledError:
            raise
        finally:
            self._pending.pop(call.id, None)
        return await self._decide(decision, call, session_id)

    def respond(self, tool_use_id: str, decision: PermissionDecision) -> None:
        """resolve 对应 Future；未知/已决 tool_use_id 仅 warning（幂等，FR-006）。"""
        entry = self._pending.get(tool_use_id)
        if entry is None:
            logger.warning(
                "未知或已决 tool_use_id=%s，忽略 respond(decision=%s)",
                tool_use_id,
                decision,
            )
            return
        future, _session_id = entry
        if future.done():
            logger.warning(
                "tool_use_id=%s 已被决（超时/断连/重复），忽略 respond(decision=%s)",
                tool_use_id,
                decision,
            )
            return
        self._pending.pop(tool_use_id, None)
        self._resolve(future, decision)

    def cancel_session(self, session_id: str) -> None:
        """断连清理：该 session 全部 pending resolve 为 deny_once，防泄漏（FR-016）。"""
        for tool_use_id, (future, sid) in list(self._pending.items()):
            if sid == session_id and not future.done():
                self._pending.pop(tool_use_id, None)
                self._resolve(future, PermissionDecision.DENY_ONCE)

    def shutdown(self) -> None:
        """daemon 优雅退出：清理全部 pending，不留未决 asyncio task（FR-017）。"""
        for tool_use_id, (future, _sid) in list(self._pending.items()):
            self._pending.pop(tool_use_id, None)
            if not future.done():
                self._resolve(future, PermissionDecision.DENY_ONCE)

    # ---- 内部 ----

    async def _wait(self, future: asyncio.Future[PermissionDecision]) -> PermissionDecision:
        """timeout_s > 0 用 wait_for（超时抛 TimeoutError），0 = 不超时直接 await。"""
        if self._timeout_s > 0:
            return await asyncio.wait_for(future, self._timeout_s)
        return await future

    async def _decide(
        self,
        decision: PermissionDecision,
        call: ToolCall,
        session_id: str,
        *,
        error: PermissionDeniedError | PermissionTimeoutError | PermissionBlacklistError | None = None,
    ) -> PermissionOutcome:
        """按决策产出 outcome + 发布 granted/denied 事件；session_* 写本 session 缓存。"""
        if decision in (
            PermissionDecision.SESSION_ALLOW,
            PermissionDecision.SESSION_DENY,
        ):
            self._cache.set(session_id, call.name, decision)
        if decision in (
            PermissionDecision.ALLOW_ONCE,
            PermissionDecision.SESSION_ALLOW,
            PermissionDecision.AUTO_ALLOW,
        ):
            await self._bus.publish(
                PermissionGrantedEvent(
                    tool_use_id=call.id,
                    session_id=session_id,
                    tool_name=call.name,
                    decision=decision,
                )
            )
            return PermissionOutcome(result=PermissionResult.GRANTED, decision=decision)
        if decision is PermissionDecision.TIMEOUT:
            await self._bus.publish(
                PermissionDeniedEvent(
                    tool_use_id=call.id,
                    session_id=session_id,
                    tool_name=call.name,
                    decision=decision,
                )
            )
            return PermissionOutcome(
                result=PermissionResult.TIMEOUT,
                decision=decision,
                error=error or PermissionTimeoutError(),
            )
        await self._bus.publish(
            PermissionDeniedEvent(
                tool_use_id=call.id,
                session_id=session_id,
                tool_name=call.name,
                decision=decision,
            )
        )
        return PermissionOutcome(
            result=PermissionResult.DENIED,
            decision=decision,
            error=error or PermissionDeniedError(),
        )

    @staticmethod
    def _level(call: ToolCall) -> PermissionLevel:
        """元数据权限级别；解析前的兜底按 ask 处理（fail-closed 由未知工具路径保证）。"""
        tool = call.resolved_tool
        return tool.permission_level if tool is not None else PermissionLevel.ASK

    @staticmethod
    def _preview(call: ToolCall) -> str:
        """参数人类可读摘要（k=v 空格连接），截断至 60 字符。"""
        args: Any = call.validated_args
        if isinstance(args, dict) and args:
            parts = [f"{k}={v}" for k, v in args.items()]
        else:
            parts = [call.arguments.strip()]
        return " ".join(parts)[:60]

    @staticmethod
    def _resolve(future: asyncio.Future[PermissionDecision], decision: PermissionDecision) -> None:
        """set_result 兜底：Future 已被超时/断连取消时静默（幂等）。"""
        try:
            future.set_result(decision)
        except (asyncio.InvalidStateError, asyncio.CancelledError):
            pass


_permissions: PermissionManager | None = None


def init_permissions() -> PermissionManager:
    """幂等初始化进程级权限管理器（需先 init_event_system）。"""
    global _permissions
    if _permissions is not None:
        return _permissions
    from kwok.config import get_config

    _permissions = PermissionManager(
        bus=get_bus(), timeout_s=get_config().permission.timeout_s
    )
    return _permissions


def get_permission_manager() -> PermissionManager:
    """取进程级权限管理器；未初始化抛错（调用方需保证 init 顺序）。"""
    if _permissions is None:
        raise RuntimeError("权限系统未初始化：请先调用 init_permissions()")
    return _permissions


def reset_permissions() -> None:
    """清空权限管理器单例（daemon 重启 / 测试隔离用）。"""
    global _permissions
    _permissions = None
