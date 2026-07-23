"""FastAPI authentication dependencies using Supabase Auth JWT."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jwt import PyJWK, decode as jwt_decode, get_unverified_header

from kyrozen.auth.context import current_user_ctx
from kyrozen.config import KyrozenConfig, get_config

security = HTTPBearer(auto_error=False)

# In-memory cache of Supabase JWKS signing keys keyed by kid.
# This avoids repeated network fetches and provides resilience when the
# Supabase JWKS endpoint is temporarily unreachable.
_jwks_cache: dict[str, Any] = {}


def _cache_path() -> Path:
    """Path to a local JWKS cache file for offline resilience."""
    return Path(os.environ.get("KYROZEN_WORKSPACE", ".")) / ".kyrozen_jwks_cache.json"


def _load_cached_jwks() -> dict[str, Any]:
    """Load JWKS keys from the local cache file."""
    path = _cache_path()
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {key.get("kid"): key for key in data.get("keys", []) if key.get("kid")}
    except (json.JSONDecodeError, OSError, KeyError):
        return {}


def _save_cached_jwks(jwks: dict[str, Any]) -> None:
    """Save JWKS keys to the local cache file."""
    path = _cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(jwks, f)
    except OSError:
        pass


def _signing_key_from_jwk(jwk: dict[str, Any]) -> Any:
    """Build a PyJWK signing key from a JWK dict."""
    return PyJWK.from_dict(jwk)


def _get_signing_key_with_retry(jwks_url: str, token: str, max_retries: int = 3) -> Any:
    """Fetch the signing key from Supabase JWKS with retries on transient errors.

    Uses ``requests`` for better TLS/SSL compatibility and falls back to a local
    cache when the network is unreachable.
    """
    header = get_unverified_header(token)
    kid = header.get("kid")

    # Try network fetch first with requests (more robust TLS handling).
    last_exc: Exception | None = None
    try:
        import requests

        for attempt in range(max_retries):
            try:
                response = requests.get(jwks_url, timeout=10)
                response.raise_for_status()
                jwks = response.json()
                _save_cached_jwks(jwks)
                for key in jwks.get("keys", []):
                    if key.get("kid") == kid:
                        return _signing_key_from_jwk(key)
                raise RuntimeError(f"No signing key found for kid {kid}")
            except Exception as exc:
                last_exc = exc
                if attempt < max_retries - 1:
                    time.sleep(0.5 * (attempt + 1))
    except ImportError:
        pass

    # Fallback to local cache.
    cached = _load_cached_jwks()
    if kid and kid in cached:
        return _signing_key_from_jwk(cached[kid])

    if last_exc is None:
        raise RuntimeError("JWKS signing key fetch failed")
    raise last_exc


def _decode_supabase_token(token: str, config: KyrozenConfig) -> dict[str, Any]:
    """Verify a Supabase JWT using JWKS when possible, falling back to HS256."""
    errors: list[str] = []
    # Allow clock skew between Supabase auth servers and the local machine.
    # Some users experience larger drift, so use a generous window while still
    # bounding token acceptance to a few minutes.
    leeway = 300

    header = get_unverified_header(token)
    kid = header.get("kid")
    alg = header.get("alg", "RS256")

    if config.supabase_url:
        jwks_url = f"{config.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"

        # Try cached key first for resilience and speed.
        if kid and kid in _jwks_cache:
            try:
                return jwt_decode(
                    token,
                    _jwks_cache[kid].key,
                    algorithms=[alg],
                    audience="authenticated",
                    leeway=leeway,
                )
            except Exception as exc:
                errors.append(f"Cached JWKS verification failed: {exc}")

        try:
            signing_key = _get_signing_key_with_retry(jwks_url, token)
            if kid:
                _jwks_cache[kid] = signing_key
            return jwt_decode(
                token,
                signing_key.key,
                algorithms=[alg],
                audience="authenticated",
                leeway=leeway,
            )
        except Exception as exc:
            errors.append(f"JWKS verification failed: {exc}")

    if config.supabase_jwt_secret and alg == "HS256":
        try:
            return jwt_decode(
                token,
                config.supabase_jwt_secret,
                algorithms=["HS256"],
                audience="authenticated",
                leeway=leeway,
            )
        except Exception as exc:
            errors.append(f"HS256 verification failed: {exc}")

    raise ValueError("Unable to verify token: " + "; ".join(errors))


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

    if not config.supabase_url and not config.supabase_jwt_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is not configured on the server",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = _decode_supabase_token(token, config)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

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
