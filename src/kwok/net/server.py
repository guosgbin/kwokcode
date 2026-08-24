from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

import kwok
from kwok.protocol.enums import ErrorCode
from kwok.protocol.errors import InvalidParamsError, LlmError, UnknownMethodError
from kwok.protocol.events import ServerStatusEvent
from kwok.protocol.rpc_model import (
    ErrorResponse,
    EventFrame,
    Request,
    Response,
    RpcFrame,
    make_error,
)
from kwok.server.event import get_bus, get_client_push

from ..server.cmd_handlers import EventHandlerManager
from .base import FRAME_LIMIT, NDJSONDecodeError, read_message, write_message
from .requset_context import RequestContext

logger = logging.getLogger(__name__)

_EXTRA_INFO_PEERNAME = "peername"


class SocketServer:

    def __init__(
            self,
            host: str,
            port: int,
            handlerManager: EventHandlerManager,
            on_disconnect: Callable[[str], None] | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._handlerManager = handlerManager
        self._bus = get_client_push()
        self._eventBus = get_bus()
        self._on_disconnect = on_disconnect
        self._server: asyncio.Server | None = None
        self._writers: set[asyncio.StreamWriter] = set()
        self._start_time = time.monotonic()

    async def serve_forever(self, stop_event: asyncio.Event | None = None) -> None:
        if stop_event is None:
            stop_event = asyncio.Event()

        self._server = await asyncio.start_server(
            self._handle_client, self._host, self._port, limit=FRAME_LIMIT
        )
        if self._server.sockets:
            bind: Any = self._server.sockets[0].getsockname()
        else:
            bind = (self._host, self._port)
        logger.info("kwok-server 监听 %s:%s", bind[0], bind[1])
        await self._publish_status("running")
        async with self._server:

            serve_task = asyncio.create_task(self._server.serve_forever())
            await stop_event.wait()
            await self._publish_status("stopping")
            await self._close_all_writers()
            self._server.close()
            await self._server.wait_closed()
            serve_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await serve_task

    async def _publish_status(self, status: Literal["running", "stopping"]) -> None:

        serverStatusEvent = ServerStatusEvent(
            status=status,
            server_version=kwok.__version__,
            uptime_ms=int((time.monotonic() - self._start_time) * 1000),
            received_at=datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S"),
        )
        await self._eventBus.publish(serverStatusEvent)

    async def _close_all_writers(self) -> None:

        writers = list(self._writers)
        for writer in writers:
            writer.close()
        for writer in writers:
            with contextlib.suppress(ConnectionError, OSError):
                await writer.wait_closed()

    async def _handle_client(
            self,
            reader: asyncio.StreamReader,
            writer: asyncio.StreamWriter
    ) -> None:
        peer = writer.get_extra_info(_EXTRA_INFO_PEERNAME, "<unknown>")
        logger.debug("client connected: %s", peer)

        connection_id = str(uuid.uuid4())
        self._writers.add(writer)

        async def send_event(method: str, params: dict[str, Any]) -> None:

            await write_message(writer, EventFrame(event=method, params=params))

        self._bus.attach(connection_id, send_event)
        try:
            while True:
                try:

                    message = await read_message(reader)
                except NDJSONDecodeError:
                    await write_message(
                        writer, RpcFrame(rpc=make_error(ErrorCode.PARSE_ERROR, "解析错误"))
                    )
                    continue
                if message is None:
                    break
                if isinstance(message, RpcFrame) and isinstance(message.rpc, Request):
                    ctx = RequestContext(request_id=message.rpc.id, connection_id=connection_id)

                    response = await self._handle_request(message.rpc, ctx)
                    await write_message(writer, RpcFrame(rpc=response))
                elif isinstance(message, EventFrame):
                    logger.warning("忽略客户端发来的事件帧：%s", message.event)
                else:
                    logger.warning("忽略客户端发来的未知 RPC 帧")
        except asyncio.CancelledError:
            raise
        finally:
            self._writers.discard(writer)
            self._bus.detach(connection_id)
            if self._on_disconnect is not None:
                self._on_disconnect(connection_id)
            writer.close()
            await writer.wait_closed()

    async def _handle_request(
            self, request: Request, ctx: RequestContext
    ) -> Response | ErrorResponse:

        try:
            result = await self._handlerManager.dispatch(request.method, request.params, ctx)
        except LlmError as exc:
            return make_error(ErrorCode.LLM_ERROR, str(exc), id=request.id)
        except UnknownMethodError:
            return make_error(ErrorCode.METHOD_NOT_FOUND, "Method not found", id=request.id)
        except InvalidParamsError as exc:
            return make_error(ErrorCode.INVALID_PARAMS, str(exc), id=request.id)
        except Exception as exc:
            logger.exception("handler 执行失败: %s", request.method)
            return make_error(ErrorCode.INVALID_REQUEST, f"handler error: {exc}", id=request.id)
        return Response(result=result, id=request.id if request.id is not None else "")
