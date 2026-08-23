from kwok.server.middleware.chain import MiddlewareChain, _init_middleware_chain
from kwok.server.middleware.middleware import Middleware

_chain: MiddlewareChain | None = None


def get_middleware_chain() -> MiddlewareChain:
    global _chain
    if _chain is None:
        _chain = MiddlewareChain()
        _init_middleware_chain(_chain)
    return _chain


__all__ = [
    "Middleware",
    "MiddlewareChain",
    "get_middleware_chain",
]
