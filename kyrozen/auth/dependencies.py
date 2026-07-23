"""FastAPI authentication dependencies using Supabase Auth JWT."""

from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt

from kyrozen.auth.context import current_user_ctx
from kyrozen.config import get_config

security = HTTPBearer(auto_error=False)


class CurrentUser:
    """Authenticated user context."""

    def __init__(
        self,
        user_id: str,
        email: str,
        name: str | None = None,
        role: str = "user",
        raw_claims: dict[str, Any] | None = None,
    ) -> None:
        self.user_id = user_id
        self.email = email
        self.name = name
        self.role = role
        self.raw_claims = raw_claims or {}

    def is_admin(self) -> bool:
        return self.role == "admin"


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> CurrentUser:
    """Validate Supabase JWT and return CurrentUser."""
    token = None
    if credentials:
        token = credentials.credentials
    else:
        token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    config = get_config()
    jwt_secret = config.supabase_jwt_secret

    if not jwt_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is not configured on the server",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(token, jwt_secret, algorithms=["HS256"], audience="authenticated")
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    email = payload.get("email", "")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing user id",
        )

    user = CurrentUser(
        user_id=user_id,
        email=email,
        name=payload.get("user_metadata", {}).get("name"),
        role=payload.get("user_metadata", {}).get("role", "user"),
        raw_claims=payload,
    )
    current_user_ctx.set(user)
    return user


async def get_current_user_optional(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> CurrentUser | None:
    """Optionally validate JWT; returns None if no credentials provided.

    If credentials are present but invalid, or authentication is not configured,
    the error is propagated rather than silently treating the request as anonymous.
    """
    token = None
    if credentials:
        token = credentials.credentials
    else:
        token = request.cookies.get("access_token")

    if not token:
        return None

    return await get_current_user(request, credentials)


async def require_admin(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if not current_user.is_admin():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user
