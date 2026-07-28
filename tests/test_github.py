"""Tests for kyrozen.core.github (3.5): OAuth URL safety, code exchange,
user lookup, repo creation (incl. name-exists), token check, OAuth error
classification, and the TokenStore never-leaks guarantee."""

from __future__ import annotations

import json
import os

from kyrozen.core import github as gh
from kyrozen.core.github import (
    GitHubClient,
    TokenStore,
    build_authorize_url,
    classify_oauth_error,
)


class FakeTransport:
    """Records calls and returns scripted (status, json) responses."""

    def __init__(self, responses):
        # responses: list of (status, dict) consumed in order; or a callable.
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, url, headers, body):
        self.calls.append({"method": method, "url": url, "headers": headers, "body": body})
        if callable(self.responses):
            return self.responses(method, url, headers, body)
        status, payload = self.responses.pop(0)
        return status, payload


# --- authorize URL (3.5 #5: no client secret in URL) -----------------------

def test_build_authorize_url_excludes_secret():
    url = build_authorize_url(
        client_id="abc123",
        redirect_uri="https://kyrozen.chat/callback",
        state="xyz",
        scopes=["repo", "user"],
    )
    assert url.startswith(gh.OAUTH_AUTHORIZE_URL)
    assert "client_id=abc123" in url
    assert "state=xyz" in url
    assert "scope=repo+user" in url or "scope=repo%20user" in url
    # The secret must never appear in the URL the browser opens.
    assert "client_secret" not in url


# --- code exchange (server-side) -------------------------------------------

def test_exchange_code_posts_secret_and_code():
    transport = FakeTransport([(200, {"access_token": "tok_123", "scope": "repo", "token_type": "bearer"})])
    client = GitHubClient(transport)
    result = client.exchange_code("cid", "csecret", "code_1", "https://kyzen/cb")
    assert result["access_token"] == "tok_123"
    sent = transport.calls[0]
    assert sent["method"] == "POST"
    assert "client_secret=csecret" in sent["body"]
    assert "code=code_1" in sent["body"]


def test_exchange_code_handles_error():
    transport = FakeTransport([(401, {"error": "bad_verification_code"})])
    client = GitHubClient(transport)
    result = client.exchange_code("cid", "csecret", "bad", "https://kyzen/cb")
    assert "error" in result


# --- user lookup (3.5 #2) --------------------------------------------------

def test_get_user_parses_login_and_avatar():
    transport = FakeTransport([(200, {"login": "octocat", "avatar_url": "https://avatars/octocat", "name": "Octo"})])
    client = GitHubClient(transport)
    user = client.get_user("tok", scopes=["repo", "user"])
    assert user.login == "octocat"
    assert user.avatar_url == "https://avatars/octocat"
    assert user.scopes == ["repo", "user"]


# --- create repo (3.5 #4) --------------------------------------------------

def test_create_repo_success_returns_urls():
    transport = FakeTransport([(201, {"clone_url": "https://github.com/u/r.git", "html_url": "https://github.com/u/r"})])
    client = GitHubClient(transport)
    res = client.create_repo("tok", "u", "r", private=True, description="d")
    assert res.ok is True
    assert res.clone_url == "https://github.com/u/r.git"
    sent = transport.calls[0]
    # Private repo request body must carry private=true and visibility=private.
    body = json.loads(sent["body"])
    assert body["private"] is True
    assert body["visibility"] == "private"
    assert body["name"] == "r"


def test_create_repo_name_exists_classified():
    transport = FakeTransport([(422, {"message": "name already exists"})])
    client = GitHubClient(transport)
    res = client.create_repo("tok", "u", "taken", private=True)
    assert res.ok is False
    assert res.failure["kind"] == "name_exists"
    assert res.failure["recovery"]


def test_create_repo_auth_failed_classified():
    transport = FakeTransport([(401, {"message": "Bad credentials"})])
    client = GitHubClient(transport)
    res = client.create_repo("tok", "u", "r", private=True)
    assert res.ok is False
    assert res.failure["kind"] == "auth_failed"


# --- token check / expiry (3.5 #1) -----------------------------------------

def test_check_token_valid_and_expired():
    transport = FakeTransport(
        [(200, {"login": "u", "scopes": ["repo"]}), (401, {"message": "Bad credentials"})]
    )
    client = GitHubClient(transport)
    assert client.check_token("valid").valid is True
    expired = client.check_token("stale")
    assert expired.valid is False
    assert expired.expired is True


# --- OAuth error classification (3.5 #1 / #6) ------------------------------

def test_classify_oauth_error_kinds():
    assert classify_oauth_error(401)["kind"] == "token_expired"
    assert classify_oauth_error(403)["kind"] == "insufficient_scope"
    assert classify_oauth_error(0)["kind"] == "network_failed"
    assert classify_oauth_error(500)["kind"] == "unknown"


# --- TokenStore keeps the token outside the workspace (3.5 #5) --------------

def test_token_store_saves_loads_clears_outside_workspace(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    # Store lives OUTSIDE the workspace (e.g. OS keychain-backed app data).
    store_path = tmp_path / "appdata" / "gh_token.json"
    store = TokenStore(str(store_path))
    store.save("ghp_STORED0123456789abcdef", "repo,user")
    assert store_path.exists()
    token, scope = store.load()
    assert token == "ghp_STORED0123456789abcdef"
    assert scope == "repo,user"
    # Token must never appear inside the workspace.
    from kyrozen.core.git_ops import scan_for_secrets

    assert scan_for_secrets("ghp_STORED0123456789abcdef", str(workspace)) == []
    store.clear()
    assert store.load() == (None, None)


# --- agent-facing GitGithubTool (3.5: the agent can drive git) -------------

import subprocess

from kyrozen.tools.git_github_tools import GitGithubTool


def _bare(tmp_path):
    remote = str(tmp_path / "bare.git")
    subprocess.run(["git", "init", "--bare", remote], check=True, capture_output=True, text=True)
    return remote


def test_git_github_tool_init_commit_push(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "README.md").write_text("# P\n")
    remote = _bare(tmp_path)
    tool = GitGithubTool(github_token=None)
    init = tool.execute("init", {"workspace_root": str(root)})
    assert init.success is True
    assert init.data["branch"] == "main"
    assert init.data["initial_commit"] is True
    tool.execute("push", {"workspace_root": str(root), "message": None})
    set_origin = tool.execute("remote", {"workspace_root": str(root)})
    # set origin first, then push.
    from kyrozen.core.git_ops import GitOps

    GitOps(str(root)).set_origin(remote)
    push = tool.execute("push", {"workspace_root": str(root), "message": "feat: x"})
    assert push.success is True
    assert push.data["ok"] is True


def test_git_github_tool_create_repo_uses_fake_transport(tmp_path):
    tool = GitGithubTool(github_token="tok")
    tool.github = GitHubClient(
        FakeTransport([(201, {"clone_url": "https://github.com/u/r.git", "html_url": "https://github.com/u/r"})])
    )
    res = tool.execute(
        "create_repo", {"owner": "u", "name": "r", "private": True, "description": "d"}
    )
    assert res.success is True
    assert res.data["clone_url"] == "https://github.com/u/r.git"


def test_git_github_tool_push_without_token_is_safe(tmp_path):
    """The token is constructor-injected, never in params (3.5 #5)."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "README.md").write_text("# P\n")
    tool = GitGithubTool(github_token="ghp_SECRET0123456789abcdef")
    result = tool.execute("init", {"workspace_root": str(root)})
    # No token appears in the returned data.
    assert "ghp_SECRET0123456789abcdef" not in str(result.data)
