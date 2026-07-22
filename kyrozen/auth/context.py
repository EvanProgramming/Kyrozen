"""Request-scoped authentication context."""

from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .dependencies import CurrentUser

current_user_ctx: ContextVar["CurrentUser | None"] = ContextVar("current_user_ctx", default=None)


def get_current_user_id() -> str | None:
    """Return the user id from the current request context, if any."""
    user = current_user_ctx.get(None)
    if user is None:
        return None
    return user.user_id
