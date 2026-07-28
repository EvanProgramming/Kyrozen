"""Tests for kyrozen.core.git_ops (3.5): init/first-commit, status, history,
remote, real push to a local bare repo, push-failure classification, and the
secret-scan zero-leak guarantee."""

from __future__ import annotations

import os
import subprocess

import pytest

from kyrozen.core import git_ops as g
from kyrozen.core.git_ops import (
    GitOps,
    PushResult,
    classify_create_repo_error,
    classify_push_error,
    scan_for_secrets,
)

GIT_BIN = "git"


def _write(path: str, content: str = "hello\n") -> None:
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)


def _git(*args: str, cwd: str) -> None:
    subprocess.run(["git", "-C", cwd, *args], check=True, capture_output=True, text=True)


def _make_bare_remote(path: str) -> None:
    subprocess.run(["git", "init", "--bare", path], check=True, capture_output=True, text=True)


@pytest.fixture()
def project(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    _write(os.path.join(root, "README.md"), "# My Project\n")
    _write(os.path.join(root, "main.py"), "print('hi')\n")
    return str(root)


# --- init + first commit (3.5 #3) ------------------------------------------

def test_init_creates_main_branch_and_first_commit(project):
    ops = GitOps(project, git_bin=GIT_BIN)
    result = ops.init()
    assert result["success"] is True
    assert result["branch"] == "main"
    assert result["initial_commit"] is True
    # .gitignore must exist and contain Kyrozen entries.
    ignore = os.path.join(project, ".gitignore")
    assert os.path.exists(ignore)
    with open(ignore, encoding="utf-8") as handle:
        text = handle.read()
    assert ".kyrozen/" in text and ".env" in text
    # A first commit exists and contains real project content.
    _, out, _ = ops._run("log", "--oneline", check=False)
    assert "initial Kyrozen project commit" in out
    assert os.path.exists(os.path.join(project, "README.md"))


def test_init_is_idempotent_and_skips_second_commit(project):
    ops = GitOps(project, git_bin=GIT_BIN)
    ops.init()
    _write(os.path.join(project, "extra.txt"), "x")
    second = ops.init()  # second init must not create another commit if none staged
    assert second["initial_commit"] is False


# --- status / history (3.5 #7) ----------------------------------------------

def test_status_reports_branch_and_changes(project):
    ops = GitOps(project, git_bin=GIT_BIN)
    ops.init()
    _write(os.path.join(project, "new.txt"), "new")
    status = ops.status()
    assert status["is_repo"] is True
    assert status["branch"] == "main"
    assert "new.txt" in status["untracked"]


def test_recent_commits_returns_history(project):
    ops = GitOps(project, git_bin=GIT_BIN)
    ops.init()
    commits = ops.recent_commits(limit=5)
    assert len(commits) == 1
    assert commits[0]["message"]
    assert commits[0]["hash"]


# --- remote (3.5 #4 / #7) ---------------------------------------------------

def test_set_origin_and_remote_url(project, tmp_path):
    ops = GitOps(project, git_bin=GIT_BIN)
    ops.init()
    remote = str(tmp_path / "bare.git")
    _make_bare_remote(remote)
    res = ops.set_origin(remote)
    assert res["success"] is True
    assert ops.remote_url() == remote


# --- real push to a local bare remote (acceptance #1 / #4) ------------------

def test_push_to_local_remote_succeeds(project, tmp_path):
    remote = str(tmp_path / "bare.git")
    _make_bare_remote(remote)
    ops = GitOps(project, git_bin=GIT_BIN)
    ops.init()
    ops.set_origin(remote)
    result = ops.push(token=None)
    assert isinstance(result, PushResult)
    assert result.ok is True
    assert result.remote_url == remote


def test_second_commit_and_push_succeeds(project, tmp_path):
    """Acceptance: a second feature modification commits and pushes."""
    remote = str(tmp_path / "bare.git")
    _make_bare_remote(remote)
    ops = GitOps(project, git_bin=GIT_BIN)
    ops.init()
    ops.set_origin(remote)
    assert ops.push(token=None).ok is True

    # Second modification.
    _write(os.path.join(project, "feature.py"), "print('feature')\n")
    assert ops.commit("feat: add feature").get("committed") is True
    second = ops.push(token=None)
    assert second.ok is True
    # The bare remote now has two commits.
    out = subprocess.run(
        ["git", "-C", remote, "rev-list", "--count", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    assert out == "2"


# --- push failure classification (3.5 #6) -----------------------------------

@pytest.mark.parametrize(
    "stderr,expected",
    [
        ("remote: Repository not found.\nfatal: Authentication failed", "auth_failed"),
        ("fatal: unable to access 'https://github.com/x/y.git': Could not resolve host", "network_failed"),
        ("! [rejected]        main -> main (fetch first)\nerror: failed to push some refs", "non_fast_forward"),
        ("error: remote origin already exists.", "remote_exists"),
        ("some other obscure failure", "unknown"),
    ],
)
def test_classify_push_error_kinds(stderr, expected):
    failure = classify_push_error(stderr)
    assert failure.kind == expected
    assert failure.recovery  # every kind has a recovery action


def test_classify_create_repo_error_name_exists():
    failure = classify_create_repo_error(422, {"message": "name already exists"})
    assert failure.kind == "name_exists"
    assert failure.recovery


# --- secret scan zero-leak guarantee (3.5 #5) ------------------------------

def test_scan_for_secrets_clean_when_no_token(project):
    ops = GitOps(project, git_bin=GIT_BIN)
    ops.init()
    remote = os.path.join(os.path.dirname(project), "bare.git")
    _make_bare_remote(remote)
    ops.set_origin(remote)
    ops.push(token=None)
    # No token was ever used, and none is planted -> zero hits.
    assert scan_for_secrets("ghp_EXAMPLETOKEN1234567890", project) == []


def test_scan_for_secrets_detects_planted_token(project):
    token = "ghp_DETECTME0123456789abcdef"
    # Plant the token inside the workspace (project file).
    _write(os.path.join(project, "leak.txt"), f"token={token}\n")
    hits = scan_for_secrets(token, project)
    assert any("leak.txt" in h for h in hits)


def test_token_never_persisted_to_git_config(project, tmp_path):
    """Push with a token must not write it into .git/config or the remote URL."""
    remote = str(tmp_path / "bare.git")
    _make_bare_remote(remote)
    ops = GitOps(project, git_bin=GIT_BIN)
    ops.init()
    # Plain (token-less) remote URL; token only travels as a one-shot header.
    ops.set_origin(remote)
    token = "ghp_SHOULDNOTLEAK0123456789abcdef"
    result = ops.push(token=token)
    assert result.ok is True
    # Inspect .git/config for the token.
    config_path = os.path.join(project, ".git", "config")
    with open(config_path, encoding="utf-8", errors="ignore") as handle:
        config_text = handle.read()
    assert token not in config_text
    # Remote URL must not embed the token.
    assert token not in (ops.remote_url() or "")
    # And the scanner must find zero hits anywhere in the workspace.
    assert scan_for_secrets(token, project) == []
