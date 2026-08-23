from __future__ import annotations

from abc import ABC, abstractmethod

from kwok.server.llm.llm_context import LlmContext
from kwok.server.llm.model import LlmResponse


class LlmProvider(ABC):
    @abstractmethod
    async def stream_chat(self, context: LlmContext) -> LlmResponse:
        ...
