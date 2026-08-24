"""KwokCode TUI 主前端：基于 textual 的全屏终端应用。

消费 kwok-server 事件流渲染界面，不持有核心逻辑（宪法 I/III/IV）。
"""

from kwok.tui.app import KwokTuiApp

__all__ = ["KwokTuiApp"]
