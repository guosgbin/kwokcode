from __future__ import annotations

import os
from dataclasses import dataclass, field

from load_dotenv import load_dotenv

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 6456
_DEFAULT_TIMEOUT: float = 3.0

_DEFAULT_LOG_LEVEL = "INFO"
_DEFAULT_LOG_FILE = "~/.kwok/logs/core.log"
_DEFAULT_LOG_FORMAT = "text"
_DEFAULT_CONFIG_PATH = "~/.kwok/config.toml"

_DEFAULT_MAX_STEPS = 20

_DEFAULT_LLM_MODEL: str = "gpt-4o-mini"
_DEFAULT_LLM_TIMEOUT: float = 60.0
_PROMPT_MAX_LENGTH: int = 4096


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
    prompt_max_length: int = _PROMPT_MAX_LENGTH


@dataclass
class KwokConfig:
    host: str = _DEFAULT_HOST
    port: int = _DEFAULT_PORT
    timeout: float = _DEFAULT_TIMEOUT
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    llm: LlmConfig = field(default_factory=LlmConfig)


def _env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value else default


def _env_int(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    return int(raw) if raw else default


def _env_float(name: str, default: float) -> float:
    raw = (os.getenv(name) or "").strip()
    return float(raw) if raw else default


def get_config() -> KwokConfig:
    config = KwokConfig()
    load_dotenv(".env", override=False)
    _get_config_from_env(config)
    return config


def _get_config_from_env(config: KwokConfig) -> None:
    config.host = _env_str("KWOK_HOST", config.host)
    config.port = _env_int("KWOK_SERVER_PORT", config.port)
    config.timeout = _env_float("KWOK_TIMEOUT", config.timeout)

    config.logging.level = _env_str("KWOK_LOG_LEVEL", config.logging.level)
    config.logging.file = _env_str("KWOK_LOG_FILE", config.logging.file)
    config.logging.format = _env_str("KWOK_LOG_FORMAT", config.logging.format)

    config.agent.max_steps = _env_int("KWOK_MAX_STEPS", config.agent.max_steps)

    config.llm.timeout = _env_float("KWOK_LLM_TIMEOUT", config.llm.timeout)
    config.llm.prompt_max_length = _env_int("KWOK_PROMPT_MAX_LENGTH", config.llm.prompt_max_length)
    config.llm.model = _env_str("OPENAI_MODEL", config.llm.model)
    config.llm.api_key = _env_str("OPENAI_API_KEY", config.llm.api_key)
    config.llm.base_url = _env_str("OPENAI_BASE_URL", config.llm.base_url)
