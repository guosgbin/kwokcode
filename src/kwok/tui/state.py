from __future__ import annotations

from dataclasses import dataclass


@dataclass
class UiState:
    """TUI 界面态：由事件流驱动更新的单一数据源，App 层据此渲染各 widget。"""

    connection_status: str = "disconnected"  # disconnected | connected | stopping | error
    session_id: str = ""
    turn_count: int = 0
    model: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    tokens_cached: int = 0
    tokens_total: int = 0
    context_pct: float = 0.0
    turn_in_flight: bool = False
    last_error: str | None = None

    @property
    def token_summary(self) -> str:
        return (
            f"in={self.tokens_in} out={self.tokens_out} "
            f"cached={self.tokens_cached} total={self.tokens_total}"
        )
