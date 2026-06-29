from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import Request, HTTPException

_HITS: dict[str, deque] = defaultdict(deque)


def check(key: str, limit: int, window_s: int, now: float | None = None) -> bool:
    """Fixed-window-ish sliding counter. Returns True if this hit is allowed."""
    now = time.monotonic() if now is None else now
    dq = _HITS[key]
    while dq and dq[0] <= now - window_s:
        dq.popleft()
    if len(dq) >= limit:
        return False
    dq.append(now)
    return True


def reset() -> None:
    _HITS.clear()


def rate_limiter(limit: int, window_s: int):
    """FastAPI dependency factory keyed by client IP + path."""
    async def _dep(request: Request) -> None:
        host = request.client.host if request.client else "anon"
        if not check(f"{host}:{request.url.path}", limit, window_s):
            raise HTTPException(status_code=429,
                                detail="Too many requests — slow down and try again shortly.")
    return _dep
