from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RequestContext:
    request_id: int | str | None
    connection_id: str
