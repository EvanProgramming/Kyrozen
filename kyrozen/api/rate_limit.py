"""Lightweight in-memory rate limiting for API endpoints.

The limiter tracks requests per client IP in a sliding window. It is
intentionally simple and does not require Redis; for multi-instance
deployments a shared store should be substituted.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock
from typing import Callable

from fastapi import HTTPException, Request


@dataclass
class _Bucket:
    """Sliding-window counter for a single client."""

    window_seconds: int
    max_requests: int
    timestamps: list[float] = field(default_factory=list)

    def is_allowed(self) -> bool:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        # Drop expired entries.
        self.timestamps = [ts for ts in self.timestamps if ts > cutoff]
        if len(self.timestamps) >= self.max_requests:
            return False
        self.timestamps.append(now)
        return True


class RateLimiter:
    """Thread-safe sliding-window rate limiter keyed by client identifier."""

    def __init__(self, window_seconds: int = 60, max_requests: int = 10) -> None:
        self.window_seconds = window_seconds
        self.max_requests = max_requests
        self._buckets: dict[str, _Bucket] = defaultdict(
            lambda: _Bucket(window_seconds=window_seconds, max_requests=max_requests)
        )
        self._lock = Lock()

    def is_allowed(self, key: str) -> bool:
        with self._lock:
            return self._buckets[key].is_allowed()

    def dependency(self, identifier: Callable[[Request], str]) -> Callable[[Request], None]:
        """Return a FastAPI dependency that enforces the limit."""

        def _check(request: Request) -> None:
            key = identifier(request)
            if not self.is_allowed(key):
                raise HTTPException(
                    status_code=429,
                    detail="请求过于频繁，请稍后再试",
                    headers={"Retry-After": str(self.window_seconds)},
                )

        return _check


def _client_ip(request: Request) -> str:
    """Extract the most reliable client IP from the request.

    Prefers the last value in X-Forwarded-For because Cloudflare appends
    the connecting client to that list.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # Take the last entry added by the closest trusted proxy.
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


# Public limiters used by the API.
waitlist_limiter = RateLimiter(window_seconds=60, max_requests=5)
auth_limiter = RateLimiter(window_seconds=60, max_requests=10)
