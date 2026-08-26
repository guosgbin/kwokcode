from __future__ import annotations

import os
from dataclasses import dataclass, field

from load_dotenv import load_dotenv  # type: ignore[import-untyped]

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 6456
_DEFAULT_TIMEOUT: float = 3.0

_DEFAULT_LOG_LEVEL = "INFO"
_DEFAULT_LOG_FILE = "~/.kwok/logs/core.log"
_DEFAULT_LOG_FORMAT = "text"
_DEFAULT_CONFIG_PATH = "~/.kwok/config.toml"
_DEFAULT_PROJECTS_DIR = "~/.kwok/projects"

_DEFAULT_MAX_STEPS = 20

_DEFAULT_LLM_MODEL: str = "gpt-4o-mini"
_DEFAULT_LLM_TIMEOUT: float = 60.0
_DEFAULT_MAX_TOKENS = 8192

_DEFAULT_PERMISSION_TIMEOUT_S: float = 60.0

_DEFAULT_TOOL_RESULT_LIMIT = 8000
_DEFAULT_TOOL_RESULT_KEEP = 4000
_DEFAULT_AUTO_THRESHOLD = 0.0
_DEFAULT_KEEP_RECENT = 5
_DEFAULT_CONTEXT_WINDOW = 128000

@dataclass
class LoggingConfig:
    level: str = _DEFAULT_LOG_LEVEL
    file: str = _DEFAULT_LOG_FILE
    format: str = _DEFAULT_LOG_FORMAT


@dataclass
class AgentConfig:
    max_steps: int = _DEFAULT_MAX_STEPS


@dataclass
class LlmConfig:
    base_url: str | None = None
    api_key: str | None = None
    model: str = _DEFAULT_LLM_MODEL
    timeout: float = _DEFAULT_LLM_TIMEOUT
    max_tokens: int = _DEFAULT_MAX_TOKENS
    # 仅配置后才传 reasoning_effort（不改变默认请求行为）
    reasoning_effort: str | None = None


@dataclass
class CompactionConfig:
    """上下文压缩配置：L1 截断参数 + L5 自动压缩阈值/窗口 + context_pct 计算窗口。"""

    tool_result_limit: int = _DEFAULT_TOOL_RESULT_LIMIT
    tool_result_keep: int = _DEFAULT_TOOL_RESULT_KEEP
    auto_threshold: float = _DEFAULT_AUTO_THRESHOLD
    keep_recent: int = _DEFAULT_KEEP_RECENT
    context_window: int = _DEFAULT_CONTEXT_WINDOW


@dataclass
class PermissionConfig:
    """权限审批配置：审批超时秒数，0 = 不超时（依赖断连清理兜底）。"""

    timeout_s: float = _DEFAULT_PERMISSION_TIMEOUT_S


@dataclass
class KwokConfig:
    host: str = _DEFAULT_HOST
    port: int = _DEFAULT_PORT
    timeout: float = _DEFAULT_TIMEOUT
    projects_dir: str = _DEFAULT_PROJECTS_DIR
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    llm: LlmConfig = field(default_factory=LlmConfig)
    permission: PermissionConfig = field(default_factory=PermissionConfig)
    compaction: CompactionConfig = field(default_factory=CompactionConfig)


def _env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value else default


def _env_str_opt(name: str, default: str | None) -> str | None:
    value = os.getenv(name)
    return value if value else default


def _env_int(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    return int(raw) if raw else default


def _env_float(name: str, default: float) -> float:
    raw = (os.getenv(name) or "").strip()
    return float(raw) if raw else default


_CONFIG: KwokConfig | None = None


def init_config() -> KwokConfig:
    """进程级配置快照：读 .env + 解析环境变量，只执行一次（幂等）。"""
    global _CONFIG
    if _CONFIG is not None:
        return _CONFIG
    config = KwokConfig()
    load_dotenv(".env", override=False)
    _get_config_from_env(config)
    _CONFIG = config
    return config


def get_config() -> KwokConfig:
    """取进程级配置快照（未初始化则抛错）。"""
    if _CONFIG is None:
        raise RuntimeError("配置未初始化：请先调用 init_config()")
    return _CONFIG


def reset_config() -> None:
    """清空配置快照（测试隔离用）。"""
    global _CONFIG
    _CONFIG = None


def _get_config_from_env(config: KwokConfig) -> None:
    config.host = _env_str("KWOK_HOST", config.host)
    config.port = _env_int("KWOK_SERVER_PORT", config.port)
    config.timeout = _env_float("KWOK_TIMEOUT", config.timeout)
    config.projects_dir = _env_str("KWOK_PROJECTS_DIR", config.projects_dir)

    config.logging.level = _env_str("KWOK_LOG_LEVEL", config.logging.level)
    config.logging.file = _env_str("KWOK_LOG_FILE", config.logging.file)
    config.logging.format = _env_str("KWOK_LOG_FORMAT", config.logging.format)

    config.agent.max_steps = _env_int("KWOK_MAX_STEPS", config.agent.max_steps)

    config.permission.timeout_s = _env_float(
        "KWOK_PERMISSION_TIMEOUT_S", config.permission.timeout_s
    )

    config.llm.timeout = _env_float("KWOK_LLM_TIMEOUT", config.llm.timeout)
    config.llm.model = _env_str("OPENAI_MODEL", config.llm.model)
    config.llm.api_key = _env_str_opt("OPENAI_API_KEY", config.llm.api_key)
    config.llm.base_url = _env_str_opt("OPENAI_BASE_URL", config.llm.base_url)
    config.llm.max_tokens = _env_int("KWOK_LLM_MAX_TOKENS", config.llm.max_tokens)
    config.llm.reasoning_effort = _env_str_opt(
        "KWOK_LLM_REASONING_EFFORT", config.llm.reasoning_effort
    )

    config.compaction.tool_result_limit = _env_int(
        "KWOK_COMPACTION_TOOL_RESULT_LIMIT", config.compaction.tool_result_limit
    )
    config.compaction.tool_result_keep = _env_int(
        "KWOK_COMPACTION_TOOL_RESULT_KEEP", config.compaction.tool_result_keep
    )
    config.compaction.auto_threshold = _env_float(
        "KWOK_COMPACTION_AUTO_THRESHOLD", config.compaction.auto_threshold
    )
    config.compaction.keep_recent = _env_int(
        "KWOK_COMPACTION_KEEP_RECENT", config.compaction.keep_recent
    )
    config.compaction.context_window = _env_int(
        "KWOK_COMPACTION_CONTEXT_WINDOW", config.compaction.context_window
    )
