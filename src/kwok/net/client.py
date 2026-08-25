from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from pydantic import ValidationError

from kwok.config import get_config
from kwok.protocol.errors import RpcConnectionError, RpcError
from kwok.protocol.events import (
    EVENT_ADAPTER,
    LLMChunkEvent,
)
from kwok.protocol.rpc_model import (
    BaseRpcReq,
    ErrorResponse,
    EventFrame,
    PromptResp,
    Request,
    Response,
    RpcFrame,
    SubscribeReq,
    SubscribeResp,
    UnsubscribeReq,
)
from kwok.protocol.topics import match

from ..util.id_generator import gen_request_id
from .base import FRAME_LIMIT, read_message, write_message

logger = logging.getLogger(__name__)

EventHandler = Callable[[Any], Awaitable[None]]


class SocketClient:

    def __init__(
            self, host: str | None = None, port: int | None = None, timeout: float | None = None
    ) -> None:
        cfg = get_config()
        self._host = host if host is not None else cfg.host
        self._port = port if port is not None else cfg.port
        self._timeout = timeout if timeout is not None else cfg.timeout
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._pending: dict[int | str, asyncio.Future[Any]] = {}
        self._reader_task: asyncio.Task[None] | None = None
        self._closed = True
        self._subs: dict[str, list[asyncio.Queue[tuple[str, Any]]]] = {}
        self._stream_queue: asyncio.Queue[tuple[str, Any]] | None = None
        self._stream_turn_id: str | None = None
        self._event_handlers: list[EventHandler] = []

    async def connect(self) -> None:

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port, limit=FRAME_LIMIT),
                timeout=self._timeout,
            )
        except (OSError, TimeoutError) as exc:
            raise RpcConnectionError(
                f"无法连接 kwok-server {self._host}:{self._port}: {exc}"
            ) from exc
        self._reader = reader
        self._writer = writer
        self._closed = False
        self._reader_task = asyncio.create_task(self._read_loop())

    def on_event(self, handler: EventHandler) -> None:

        self._event_handlers.append(handler)

    async def _read_loop(self) -> None:

        if self._reader is None:
            raise RuntimeError("连接未建立，请先建立连接")
        try:
            while True:
                message = await read_message(self._reader)
                if message is None:
                    break
                await self._route(message)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._fail_all(RpcConnectionError(f"连接中断: {exc}"))
        finally:
            self._fail_all(RpcConnectionError("连接已关闭"))

    async def _route(self, message: RpcFrame | EventFrame) -> None:

        if isinstance(message, EventFrame):
            await self._route_event(message.event, message.params)
            return
        await self._route_rpc_response(message)

    async def _route_rpc_response(self, message: RpcFrame) -> None:
        rpc = message.rpc
        if not isinstance(rpc, (Response, ErrorResponse)):
            logger.warning("无法处理的 RPC 帧负载类型：%s", type(rpc))
            return
        if rpc.id is None:
            return
        future = self._pending.pop(rpc.id, None)
        if future is None or future.done():
            return
        if isinstance(rpc, ErrorResponse):
            future.set_exception(RpcError(rpc.error.code, rpc.error.message, rpc.error.data))
        else:
            future.set_result(rpc.result)

            if self._stream_queue is not None and self._stream_turn_id is None:
                try:
                    ack = PromptResp.model_validate(rpc.result)
                except ValidationError:
                    pass
                else:
                    self._stream_turn_id = ack.turn_id

    async def _route_event(self, method: str, params: Any) -> None:

        try:
            event = EVENT_ADAPTER.validate_python({} if params is None else params)
        except ValidationError:
            logger.warning("无法解析事件（type=%s）", method)
            return

        if self._stream_queue is not None and self._stream_turn_id is not None:
            if isinstance(event, LLMChunkEvent) and event.turn_id == self._stream_turn_id:
                self._stream_queue.put_nowait(("chunk", event.delta))

        for pattern, queues in self._subs.items():
            if match(pattern, method):
                for queue in queues:
                    queue.put_nowait(("event", event))

        for handler in self._event_handlers:
            try:
                await handler(event)
            except Exception:
                logger.warning("事件回调失败 type=%s", method, exc_info=True)

    def _fail_all(self, exc: Exception) -> None:

        self._closed = True
        for future in self._pending.values():
            if not future.done():
                future.set_exception(exc)
        self._pending.clear()
        if self._stream_queue is not None:
            self._stream_queue.put_nowait(("closed", exc))
        for queue in self._all_sub_queues():
            queue.put_nowait(("closed", exc))

    def _all_sub_queues(self) -> list[asyncio.Queue[tuple[str, Any]]]:

        seen: set[int] = set()
        result: list[asyncio.Queue[tuple[str, Any]]] = []
        for queues in self._subs.values():
            for queue in queues:
                if id(queue) not in seen:
                    seen.add(id(queue))
                    result.append(queue)
        return result

    def _remove_sub_queue(
            self, patterns: list[str], queue: asyncio.Queue[tuple[str, Any]]
    ) -> None:

        for pattern in patterns:
            queues = self._subs.get(pattern)
            if queues is None:
                continue
            if queue in queues:
                queues.remove(queue)
            if not queues:
                del self._subs[pattern]

    async def call(
            self, params: BaseRpcReq, *, timeout: float | None = None
    ) -> Any:

        if self._closed or self._writer is None or self._reader is None:
            raise RpcConnectionError("客户端未连接")
        raw = params.model_dump(mode="json", exclude={"method"})
        method = params.method
        req_id = gen_request_id()
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._pending[req_id] = future
        request = Request(method=method, params=raw, id=req_id)
        try:
            await write_message(self._writer, RpcFrame(rpc=request))
        except (OSError, ConnectionError) as exc:
            pending_future = self._pending.pop(req_id) if req_id in self._pending else None
            if pending_future is not None:
                pending_future.cancel()
            raise RpcConnectionError(f"发送失败: {exc}") from exc
        try:
            # timeout 覆盖：None 走默认（self._timeout）；慢 RPC（如压缩）由调用方显式放宽
            wait_timeout = self._timeout if timeout is None else timeout
            return await asyncio.wait_for(future, timeout=wait_timeout)
        except TimeoutError:
            pending_future = self._pending.pop(req_id) if req_id in self._pending else None
            if pending_future is not None:
                pending_future.cancel()
            raise RpcConnectionError(f"等待响应超时（{self._timeout}s）") from None

    async def subscribe(self, patterns: list[str]) -> tuple[str, AsyncIterator[Any]]:

        if self._closed or self._writer is None or self._reader is None:
            raise RpcConnectionError("客户端未连接")
        queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
        for pattern in patterns:
            self._subs.setdefault(pattern, []).append(queue)
        try:
            ack = SubscribeResp.model_validate(
                await self.call(SubscribeReq(patterns=patterns))
            )
        except BaseException:
            self._remove_sub_queue(patterns, queue)
            raise

        async def _events() -> AsyncIterator[Any]:
            try:
                while True:
                    kind, payload = await queue.get()
                    if kind == "event":
                        yield payload
                    elif kind == "closed":
                        raise payload
            finally:
                self._remove_sub_queue(patterns, queue)
                with contextlib.suppress(RpcError, RpcConnectionError):
                    await self.call(UnsubscribeReq(patterns=patterns))

        return ack.connection_id, _events()

    async def unsubscribe(self, patterns: list[str]) -> None:

        await self.call(UnsubscribeReq(patterns=patterns))

    async def stream(self, method: str, params: Any = None) -> AsyncIterator[str]:

        if self._closed or self._writer is None or self._reader is None:
            raise RpcConnectionError("客户端未连接")
        if self._stream_queue is not None:
            raise RpcConnectionError("已有进行中的流，当前仅支持串行流")

        try:
            SubscribeResp.model_validate(
                await self.call(SubscribeReq(patterns=["chat.*"]))
            )
        except ValidationError as exc:
            raise RpcConnectionError(f"订阅响应无法识别: {exc}") from exc
        req_id = gen_request_id()
        self._stream_queue = asyncio.Queue()

        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._pending[req_id] = future
        request = Request(method=method, params=params, id=req_id)
        try:
            await write_message(self._writer, RpcFrame(rpc=request))
        except (OSError, ConnectionError) as exc:
            self._pending.pop(req_id, None)
            self._reset_stream_state()
            raise RpcConnectionError(f"发送失败: {exc}") from exc
        try:
            try:
                ack = PromptResp.model_validate(
                    await asyncio.wait_for(future, timeout=self._timeout)
                )
                self._stream_turn_id = ack.turn_id
            except TimeoutError:
                raise RpcConnectionError(f"等待 chat ack 超时（{self._timeout}s）") from None
            except ValidationError as exc:
                raise RpcConnectionError(f"chat ack 无法识别: {exc}") from exc

            while True:
                try:
                    kind, payload = await asyncio.wait_for(
                        self._stream_queue.get(), timeout=self._timeout
                    )
                except TimeoutError:
                    raise RpcConnectionError(f"等待流响应超时（{self._timeout}s）") from None
                if kind == "chunk":
                    yield payload
                elif kind == "error":
                    raise payload
                elif kind == "closed":
                    raise payload
                else:
                    return
        finally:
            self._pending.pop(req_id, None)
            self._reset_stream_state()
            with contextlib.suppress(RpcError, RpcConnectionError):
                await self.call(UnsubscribeReq(patterns=["chat.*"]))

    def _reset_stream_state(self) -> None:

        self._stream_queue = None
        self._stream_turn_id = None

    async def close(self) -> None:

        self._closed = True
        if self._reader_task is not None:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None
        if self._writer is not None:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except (ConnectionError, OSError):
                pass
            self._writer = None

    async def __aenter__(self) -> SocketClient:
        await self.connect()
        return self

    async def __aexit__(self, *_exc_info: Any) -> None:
        await self.close()
