"""GitHub API client + OAuth helpers for Kyrozen (3.5).

The transport is injectable so the logic is fully unit-testable without
network access. The default transport uses :mod:`urllib.request`.

Token safety (3.5 #5): the client never writes the token to disk, logs, or
project files. ``TokenStore`` persists the token to an explicit path that
must live *outside* the workspace (e.g. the OS keychain-backed app data dir);
``scan_for_secrets`` in :mod:`kyrozen.core.git_ops` verifies it never leaks
into the workspace. The OAuth **client secret** is only used server-side for
the code→token exchange and is never embedded in the authorize URL.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Optional, Tuple

OAUTH_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
OAUTH_TOKEN_URL = "https://github.com/login/oauth/access_token"
API_BASE = "https://api.github.com"

OAUTH_ERROR_KINDS = ("token_expired", "insufficient_scope", "revoked", "callback_failed", "network_failed", "unknown")

OAUTH_RECOVERY: dict[str, str] = {
    "token_expired": "GitHub 授权已过期或已撤销。请点击「重新连接 GitHub」完成浏览器授权。",
    "insufficient_scope": "GitHub 令牌权限不足（缺少 repo 或 user 权限）。请重新连接并授权所需 scope。",
    "revoked": "GitHub 授权已被撤销。请重新连接 GitHub 账号。",
    "callback_failed": "GitHub 回调失败。请检查浏览器是否完成授权，并重试连接。",
    "network_failed": "无法连接 GitHub。请检查网络连接后重试。",
    "unknown": "GitHub 操作失败。请稍后重试。",
}

Transport = Callable[[str, str, dict, Optional[str]], Tuple[int, Any]]


@dataclass
class GitHubUser:
    login: str
    avatar_url: str
    name: Optional[str] = None
    html_url: Optional[str] = None
    scopes: Optional[list[str]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "login": self.login,
            "avatar_url": self.avatar_url,
            "name": self.name,
            "html_url": self.html_url,
            "scopes": self.scopes,
        }


@dataclass
class CreateRepoResult:
    ok: bool
    html_url: Optional[str] = None
    clone_url: Optional[str] = None
    failure: Optional[dict[str, str]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "html_url": self.html_url,
            "clone_url": self.clone_url,
            "failure": self.failure,
        }


@dataclass
class TokenCheck:
    valid: bool
    expired: bool
    scopes: Optional[list[str]] = None

    def to_dict(self) -> dict[str, Any]:
        return {"valid": self.valid, "expired": self.expired, "scopes": self.scopes}


def _default_transport(method: str, url: str, headers: dict, body: Optional[str]) -> Tuple[int, Any]:
    data = body.encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
            raw = response.read().decode("utf-8", "ignore")
            status = response.status
    except urllib.error.HTTPError as exc:  # pragma: no cover - network path
        raw = exc.read().decode("utf-8", "ignore") if exc.fp else ""
        status = exc.code
    except Exception:  # pragma: no cover - network path (DNS / timeout)
        return 0, {}
    try:
        parsed = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        parsed = {}
    return status, parsed


def build_authorize_url(
    client_id: str,
    redirect_uri: str,
    state: str,
    scopes: list[str],
    *,
    allow_signup: bool = True,
) -> str:
    """Build the OAuth authorize URL. The client *secret* is never included."""
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(scopes),
        "state": state,
        "allow_signup": "true" if allow_signup else "false",
    }
    return f"{OAUTH_AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"


class GitHubClient:
    """GitHub API client. Pass a custom ``transport`` to test without network."""

    def __init__(self, transport: Transport = _default_transport) -> None:
        self.transport = transport

    # --- OAuth (server-side code exchange) -----------------------------------

    def exchange_code(self, client_id: str, client_secret: str, code: str, redirect_uri: str) -> dict[str, Any]:
        body = urllib.parse.urlencode(
            {
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            }
        )
        status, data = self.transport(
            "POST", OAUTH_TOKEN_URL,
            {"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
            body,
        )
        if status == 200 and isinstance(data, dict) and data.get("access_token"):
            return {"access_token": data["access_token"], "scope": data.get("scope", ""), "token_type": data.get("token_type", "bearer")}
        error = data.get("error_description") or data.get("error") or f"HTTP {status}"
        return {"error": error}

    # --- user / repos ---------------------------------------------------------

    def get_user(self, token: str, scopes: Optional[list[str]] = None) -> GitHubUser:
        status, data = self.transport(
            "GET", f"{API_BASE}/user",
            {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
            None,
        )
        if status != 200 or not isinstance(data, dict):
            raise GitHubApiError(status, data.get("message") if isinstance(data, dict) else "request failed")
        return GitHubUser(
            login=str(data.get("login", "")),
            avatar_url=str(data.get("avatar_url", "")),
            name=data.get("name"),
            html_url=data.get("html_url"),
            scopes=scopes,
        )

    def create_repo(
        self,
        token: str,
        owner: str,
        name: str,
        private: bool,
        description: str = "",
        *,
        create_under_org: bool = False,
    ) -> CreateRepoResult:
        url = f"{API_BASE}/orgs/{owner}/repos" if create_under_org else f"{API_BASE}/user/repos"
        payload = json.dumps(
            {
                "name": name,
                "description": description or "",
                "private": bool(private),
                "auto_init": False,
                "visibility": "private" if private else "public",
            }
        )
        status, data = self.transport(
            "POST", url,
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
            },
            payload,
        )
        if status in (200, 201) and isinstance(data, dict) and data.get("clone_url"):
            return CreateRepoResult(ok=True, html_url=data.get("html_url"), clone_url=data.get("clone_url"))
        from kyrozen.core.git_ops import classify_create_repo_error

        failure = classify_create_repo_error(status, data).__dict__
        return CreateRepoResult(ok=False, failure=failure)

    def check_token(self, token: str) -> TokenCheck:
        status, data = self.transport(
            "GET", f"{API_BASE}/user",
            {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
            None,
        )
        if status == 200:
            scopes: Optional[list[str]] = None
            if isinstance(data, dict) and data.get("scopes"):
                scopes = list(data["scopes"])
            return TokenCheck(valid=True, expired=False, scopes=scopes)
        # 401 = expired/revoked; 403 = insufficient scope.
        return TokenCheck(valid=False, expired=(status == 401), scopes=None)


class GitHubApiError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def classify_oauth_error(status: int, body: Any = None) -> dict[str, str]:
    """Map an OAuth/API error to a kind + recovery message (3.5 #1 / #6)."""
    message = ""
    if isinstance(body, dict):
        message = str(body.get("message") or body.get("error_description") or "")
    if status in (401, 403):
        if status == 403 or "scope" in message.lower():
            kind = "insufficient_scope"
        elif status == 401:
            kind = "token_expired"
        else:
            kind = "revoked"
    elif status == 0:
        kind = "network_failed"
    else:
        kind = "unknown"
    return {"kind": kind, "reason": message or f"HTTP {status}", "recovery": OAUTH_RECOVERY[kind]}


class TokenStore:
    """Persists the GitHub token to a path *outside* the workspace.

    Never call this with a path inside the project workspace.
    """

    def __init__(self, store_path: str) -> None:
        self.store_path = store_path

    def save(self, token: str, scope: Optional[str] = None) -> None:
        directory = os.path.dirname(self.store_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(self.store_path, "w", encoding="utf-8") as handle:
            json.dump({"github_access_token": token, "scope": scope or ""}, handle)

    def load(self) -> Tuple[Optional[str], Optional[str]]:
        if not os.path.exists(self.store_path):
            return None, None
        try:
            with open(self.store_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            return data.get("github_access_token"), data.get("scope") or None
        except (json.JSONDecodeError, OSError):
            return None, None

    def clear(self) -> None:
        if os.path.exists(self.store_path):
            os.remove(self.store_path)
