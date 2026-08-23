from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

ToolImpl = Callable[[dict[str, Any]], str]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    execute: ToolImpl
    strict: bool = True

    @property
    def schema(self) -> dict[str, object]:

        params = dict(self.parameters)
        if self.strict:
            params.setdefault("additionalProperties", False)
        function: dict[str, object] = {
            "name": self.name,
            "description": self.description,
            "parameters": params,
        }
        if self.strict:
            function["strict"] = True
        return {"type": "function", "function": function}


_REGISTRY: dict[str, Tool] = {}


def register(tool: Tool) -> None:
    _REGISTRY[tool.name] = tool
