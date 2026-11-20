"""Small in-memory sliding-window rate limiter.

Good enough for a single API process. With several API replicas the counters would
need to live in Redis (see docs/TECHNICAL_DECISIONS.md, TD-009).
"""

import threading
import time
from collections import defaultdict, deque

from fastapi import Request

from app.config import get_settings
from app.errors import AppError

_lock = threading.Lock()
_hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)


def reset() -> None:
    with _lock:
        _hits.clear()


def check_rate(bucket: str, key: str, limit: int, window_s: int = 60) -> None:
    if not get_settings().rate_limit_enabled:
        return
    now = time.monotonic()
    with _lock:
        q = _hits[(bucket, key)]
        while q and now - q[0] > window_s:
            q.popleft()
        if len(q) >= limit:
            retry_after = max(1, int(window_s - (now - q[0])))
            raise AppError(
                429,
                "rate_limited",
                f"Too many requests. Retry in {retry_after}s.",
                headers={"Retry-After": str(retry_after)},
            )
        q.append(now)


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"
