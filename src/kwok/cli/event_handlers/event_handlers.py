from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

from kwok.protocol.events import (
    BaseEvent,
    EventType,
    LLMChunkEvent,
    LLMUsageEvent,
    ServerStatusEvent,
    StepFinishEvent,
    StepStartEvent,
    ToolCallFinishEvent,
    ToolCallStartEvent,
    TurnErrorEvent,
    TurnFinishEvent,
    TurnStartEvent,
)

TEvent = TypeVar("TEvent", bound=BaseEvent)
EventHandler = Callable[[TEvent], Awaitable[None]]


class EventHandlerManager:

    def __init__(self) -> None:
        self._handlers: dict[EventType, EventHandler[BaseEvent]] = {}

    def register(
            self, event_type: EventType
    ) -> Callable[[EventHandler[BaseEvent]], EventHandler[BaseEvent]]:
        def decorator(fn: EventHandler[BaseEvent]) -> EventHandler[BaseEvent]:
            if event_type in self._handlers:
                raise ValueError(f"事件类型重复注册 handler：{event_type}")
            self._handlers[event_type] = fn
            return fn

        return decorator

    def types(self) -> list[EventType]:
        return sorted(self._handlers)

    async def dispatch(self, event: BaseEvent) -> None:
        handler = self._handlers.get(event.type)
        if handler is not None:
            await handler(event)


event_mgr = EventHandlerManager()


@event_mgr.register(EventType.LLM_CHUNK)
async def on_chat_chunk(event: BaseEvent) -> None:
    assert isinstance(event, LLMChunkEvent)
    print(event.delta, end="", flush=True)


@event_mgr.register(EventType.LLM_USAGE)
async def on_llm_usage(event: BaseEvent) -> None:
    assert isinstance(event, LLMUsageEvent)
    print(
        f"[llm] {event.turn_id} step_id={event.step_id} "
        f"in={event.input_tokens} out={event.output_tokens} "
        f"cached={event.cached_tokens} total={event.total_tokens}"
    )


@event_mgr.register(EventType.TURN_START)
async def on_turn_start(event: BaseEvent) -> None:
    assert isinstance(event, TurnStartEvent)
    print(f"[turn] {event.turn_id} 对话开始")


@event_mgr.register(EventType.TURN_FINISH)
async def on_turn_finish(event: BaseEvent) -> None:
    assert isinstance(event, TurnFinishEvent)
    print(f"[turn] {event.turn_id} 对话结束")


@event_mgr.register(EventType.TURN_ERROR)
async def on_turn_error(event: BaseEvent) -> None:
    assert isinstance(event, TurnErrorEvent)
    print(
        f"[{event.type}] {event.turn_id} "
        f"对话异常, code={event.code}, message={event.message}"
    )


@event_mgr.register(EventType.STEP_START)
async def on_step_start(event: BaseEvent) -> None:
    assert isinstance(event, StepStartEvent)
    print(f"[step-{event.step_id}] {event.turn_id} 步骤 {event.step_id}开始")


@event_mgr.register(EventType.STEP_FINISH)
async def on_step_finish(event: BaseEvent) -> None:
    assert isinstance(event, StepFinishEvent)
    print(
        f"[step-{event.step_id}] {event.turn_id} 步骤 {event.step_id}结束, "
        f"finish={event.finish_reason}"
    )


@event_mgr.register(EventType.TOOL_CALL_START)
async def on_tool_call_start(event: BaseEvent) -> None:
    assert isinstance(event, ToolCallStartEvent)
    print(f"[tool] {event.name} 开始")


@event_mgr.register(EventType.TOOL_CALL_FINISH)
async def on_tool_call_finish(event: BaseEvent) -> None:
    assert isinstance(event, ToolCallFinishEvent)
    print(f"[tool] tool={event.name} result={event.result[:20]}")


@event_mgr.register(EventType.SERVER_STATUS)
async def on_server_status(event: BaseEvent) -> None:
    assert isinstance(event, ServerStatusEvent)
    print(
        f"\n[server] {event.status} | {event.server_version} | uptime={event.uptime_ms}ms"
    )
