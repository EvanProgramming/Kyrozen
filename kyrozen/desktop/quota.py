"""Quota management for desktop client model proxy requests.

MVP implementation stores usage in memory and reads limits from configuration.
Future versions can persist usage to the database and integrate with billing.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any


@dataclass
class QuotaStatus:
    """Result of a quota check."""

    allowed: bool
    reason: str
    used: int
    limit: int
    remaining: int


class QuotaManager:
    """Tracks per-user token usage and enforces configurable limits."""

    def __init__(self, default_limit: int = 0) -> None:
        """Initialize the manager.

        ``default_limit`` is the fallback per-user token limit. A value of 0
        means unlimited, which is convenient for self-hosted or early testing
        deployments. Set a positive value to enforce quotas.
        """
        self._default_limit = max(0, default_limit)
        self._user_limits: dict[str, int] = {}
        self._usage: dict[str, int] = {}
        self._lock = threading.Lock()

    def set_user_limit(self, user_id: str, limit: int) -> None:
        """Set or update a per-user token limit."""
        with self._lock:
            self._user_limits[user_id] = max(0, limit)

    def check_quota(self, user_id: str, estimated_tokens: int = 0) -> QuotaStatus:
        """Return whether the user can consume the estimated tokens."""
        with self._lock:
            limit = self._user_limits.get(user_id, self._default_limit)
            used = self._usage.get(user_id, 0)
        if limit == 0:
            return QuotaStatus(
                allowed=True,
                reason="Quota unlimited",
                used=used,
                limit=0,
                remaining=-1,
            )
        remaining = max(0, limit - used)
        if estimated_tokens > remaining:
            return QuotaStatus(
                allowed=False,
                reason=f"Quota exceeded: {used}/{limit} tokens used",
                used=used,
                limit=limit,
                remaining=remaining,
            )
        return QuotaStatus(
            allowed=True,
            reason="Quota ok",
            used=used,
            limit=limit,
            remaining=remaining,
        )

    def record_usage(self, user_id: str, prompt_tokens: int, completion_tokens: int) -> None:
        """Add consumed tokens to the user's running total."""
        with self._lock:
            self._usage[user_id] = self._usage.get(user_id, 0) + prompt_tokens + completion_tokens

    def get_usage(self, user_id: str) -> int:
        """Return the current token usage for a user."""
        with self._lock:
            return self._usage.get(user_id, 0)

    def reset_usage(self, user_id: str | None = None) -> None:
        """Reset usage for one user or all users."""
        with self._lock:
            if user_id is None:
                self._usage.clear()
            else:
                self._usage.pop(user_id, None)

    def to_dict(self) -> dict[str, Any]:
        """Return a snapshot of limits and usage for debugging."""
        with self._lock:
            return {
                "default_limit": self._default_limit,
                "user_limits": dict(self._user_limits),
                "usage": dict(self._usage),
            }
