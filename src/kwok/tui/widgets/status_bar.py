from __future__ import annotations

from textual.widgets import Static

from kwok.tui.state import UiState


class StatusBar(Static):
    """底部状态栏：由 App 在 UiState 变更后显式调用 render_state 刷新。"""

    def render_state(self, state: UiState) -> None:
        if state.connection_status == "connected":
            conn = "[#4EBF71]● connected[/#4EBF71]"
        elif state.connection_status in ("error", "disconnected"):
            conn = "[#B93C5B]● " + state.connection_status + "[/#B93C5B]"
        else:
            conn = f"[dim]● {state.connection_status}[/dim]"
        flight = (
            "[bold #FEA62B]● RUNNING[/bold #FEA62B]"
            if state.turn_in_flight
            else "[dim]idle[/dim]"
        )
        filled = min(20, max(0, int(state.context_pct * 20)))
        bar = "█" * filled + "░" * (20 - filled)
        if state.context_pct >= 0.85:
            ctx = f"ctx:{state.context_pct * 100:.1f}% [#B93C5B]{bar}[/#B93C5B]"
        elif state.context_pct >= 0.70:
            ctx = f"ctx:{state.context_pct * 100:.1f}% [#FEA62B]{bar}[/#FEA62B]"
        else:
            ctx = f"ctx:{state.context_pct * 100:.1f}% {bar}"
        parts = [
            conn,
            f"sess={state.session_id or '-'}",
            f"model={state.model or '-'}",
            f"[dim]tokens {state.token_summary}[/dim]",
            ctx,
            flight,
        ]
        self.update("  ·  ".join(parts))
