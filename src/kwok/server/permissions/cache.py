from __future__ import annotations

from kwok.protocol.enums import PermissionDecision


class SessionDecisionCache:
    """本 session 会话级决策内存缓存。

    键 (session_id, tool_name)，daemon 存活期内有效；不落盘，daemon 重启即整体丢弃（FR-013）。
    """

    def __init__(self) -> None:
        self._entries: dict[tuple[str, str], PermissionDecision] = {}

    def get(self, session_id: str, tool_name: str) -> PermissionDecision | None:
        return self._entries.get((session_id, tool_name))

    def set(self, session_id: str, tool_name: str, decision: PermissionDecision) -> None:
        self._entries[(session_id, tool_name)] = decision

    def clear(self) -> None:
        self._entries.clear()
