from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from pydantic import BaseModel

type ToolImpl = Callable[[dict[str, Any]], dict[str, Any]]


class PermissionLevel(StrEnum):
    """工具权限级别：仅定义字段，不接入执行流（后续审批 feature 消费）。"""

    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


class RiskLevel(StrEnum):
    """工具风险级别：仅定义字段，不接入执行流。"""

    READONLY = "readonly"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ReadWrite(StrEnum):
    """工具读写属性（分类维度）。"""

    READ = "read"
    WRITE = "write"
    EXEC = "exec"


@dataclass(frozen=True)
class ToolCategory:
    """工具分类：业务类型 + 读写属性，供 find 过滤。"""

    business_type: str = "file"
    read_write: ReadWrite = ReadWrite.READ


@dataclass(frozen=True)
class RetryStrategy:
    """指数退避重试策略。max_retries 为首次失败后的追加重试次数。"""

    max_retries: int = 0
    backoff_seconds: float = 0.5
    backoff_multiplier: float = 2.0
    retryable_types: tuple[type[Exception], ...] = (TimeoutError, ConnectionError, OSError)

    def is_retryable(self, error: Exception) -> bool:
        """该异常类型是否可重试（isinstance 匹配 retryable_types）。"""
        return isinstance(error, self.retryable_types)


class ToolError(Exception):
    """工具失败的结构化错误通道：payload 经 error_model 校验或直接序列化返回给 LLM。"""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        super().__init__(str(payload))


@dataclass(frozen=True)
class Tool:
    """工具元数据 + 执行函数。parameters 由 input_model 派生，不存储。"""

    name: str
    description: str
    input_model: type[BaseModel]
    execute: ToolImpl
    strict: bool = True
    output_model: type[BaseModel] | None = None
    error_model: type[BaseModel] | None = None
    permission_level: PermissionLevel = PermissionLevel.ASK
    risk_level: RiskLevel = RiskLevel.READONLY
    category: ToolCategory = field(default_factory=ToolCategory)
    timeout: float | None = None
    all_timeout: float | None = None
    retry_policy: RetryStrategy | None = None

    @property
    def parameters(self) -> dict[str, Any]:
        """入参 JSON Schema：由 input_model 现算派生。"""
        return schema_from_pydantic(self.input_model)

    @property
    def schema(self) -> dict[str, object]:
        """OpenAI function schema：仅暴露 name/description/parameters(+strict)。"""

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


def schema_from_pydantic(model: type[BaseModel]) -> dict[str, Any]:
    """pydantic 模型类 → 干净 JSON Schema dict（递归去掉 title 噪音）。"""
    schema = model.model_json_schema()

    def _clean(node: dict[str, Any]) -> dict[str, Any]:
        return {
            k: _clean(v) if isinstance(v, dict) else v
            for k, v in node.items()
            if k != "title"
        }

    return _clean(schema)
