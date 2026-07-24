"""Token management for desktop client authentication.

The desktop client uses a two-step token flow:

1. Website requests a short-lived "open token" bound to a user/project.
2. Desktop client exchanges the open token for long-lived credentials
   (refresh token + WebSocket token) via /api/desktop/verify-token.
"""

from __future__ import annotations

import secrets
import time
from typing import Any


# In-memory token stores. For production these should be moved to Redis or the
# primary database so they survive server restarts and work across multiple
# server instances.
_OPEN_TOKENS: dict[str, dict[str, Any]] = {}
_REFRESH_TOKENS: dict[str, dict[str, Any]] = {}
_WS_TOKENS: dict[str, dict[str, Any]] = {}

_OPEN_TOKEN_TTL_SECONDS = 5 * 60  # 5 minutes
_REFRESH_TOKEN_TTL_SECONDS = 30 * 24 * 60 * 60  # 30 days
_WS_TOKEN_TTL_SECONDS = 24 * 60 * 60  # 24 hours


def _now() -> int:
    return int(time.time())


def _purge_expired(store: dict[str, dict[str, Any]]) -> None:
    now = _now()
    expired = [key for key, value in store.items() if value.get("exp", 0) < now]
    for key in expired:
        store.pop(key, None)


class DesktopTokenManager:
    """Generate and validate desktop client tokens."""

    @staticmethod
    def create_open_token(user_id: str, project_id: str | None = None) -> str:
        """Create a short-lived single-use token for launching the desktop app."""
        _purge_expired(_OPEN_TOKENS)
        token = secrets.token_urlsafe(32)
        _OPEN_TOKENS[token] = {
            "user_id": user_id,
            "project_id": project_id,
            "exp": _now() + _OPEN_TOKEN_TTL_SECONDS,
            "used": False,
        }
        return token

    @staticmethod
    def consume_open_token(token: str) -> dict[str, Any] | None:
        """Validate and consume an open token, returning user/project info."""
        _purge_expired(_OPEN_TOKENS)
        data = _OPEN_TOKENS.pop(token, None)
        if data is None or data.get("used"):
            return None
        data["used"] = True
        return {"user_id": data["user_id"], "project_id": data.get("project_id")}

    @staticmethod
    def create_credentials(user_id: str) -> dict[str, str]:
        """Create refresh token and WebSocket token for a verified desktop client."""
        _purge_expired(_REFRESH_TOKENS)
        _purge_expired(_WS_TOKENS)

        refresh_token = secrets.token_urlsafe(32)
        _REFRESH_TOKENS[refresh_token] = {
            "user_id": user_id,
            "exp": _now() + _REFRESH_TOKEN_TTL_SECONDS,
        }

        ws_token = secrets.token_urlsafe(32)
        _WS_TOKENS[ws_token] = {
            "user_id": user_id,
            "exp": _now() + _WS_TOKEN_TTL_SECONDS,
        }

        return {
            "refresh_token": refresh_token,
            "ws_token": ws_token,
        }

    @staticmethod
    def verify_refresh_token(token: str) -> str | None:
        """Return user_id if the refresh token is valid."""
        _purge_expired(_REFRESH_TOKENS)
        data = _REFRESH_TOKENS.get(token)
        return data["user_id"] if data else None

    @staticmethod
    def verify_ws_token(token: str) -> str | None:
        """Return user_id if the WebSocket token is valid."""
        _purge_expired(_WS_TOKENS)
        data = _WS_TOKENS.get(token)
        return data["user_id"] if data else None


def verify_desktop_token(token: str) -> dict[str, Any] | None:
    """Backward-compatible helper to verify a refresh token."""
    user_id = DesktopTokenManager.verify_refresh_token(token)
    if user_id is None:
        return None
    return {"user_id": user_id}
