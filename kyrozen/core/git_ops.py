"""Local Git operations for Kyrozen project workspaces (3.5).

All operations run against the project workspace root via the ``git`` CLI.
Credentials are never persisted: push uses a one-shot ``http.extraHeader``
supplied on the command line, and the token is never written to
``.git/config``, the remote URL, logs, or any project file. See
``scan_for_secrets`` and the tests for the zero-leak guarantee.

This module is the single source of truth for the push-failure
classification (five kinds required by the plan: repo-name-exists,
remote-already-exists, auth-failed, network-failed, non-fast-forward).
"""

from __future__ import annotations

import base64
import os
import subprocess
from dataclasses import dataclass, field
from typing import Any, Optional

DEFAULT_GIT_BIN = "git"
DEFAULT_MAIN_BRANCH = "main"
KYROZEN_AUTHOR_NAME = "Kyrozen"
KYROZEN_AUTHOR_EMAIL = "kyrozen@users.noreply.github.com"
DEFAULT_GITIGNORE_ENTRIES = (
    ".kyrozen/",
    ".env",
    "__pycache__/",
    "node_modules/",
    "dist/",
    "dist-electron/",
)

# --- Push / create-repo failure taxonomy (3.5 requirement #6) ----------------

PUSH_FAILURE_KINDS = (
    "auth_failed",        # token invalid / insufficient scope / 401-403
    "network_failed",     # DNS / connection / timeout
    "non_fast_forward",   # remote has commits we don't have
    "remote_exists",      # `origin` remote already exists
    "unknown",            # anything else
)

CREATE_REPO_FAILURE_KINDS = (
    "name_exists",        # 422 — repo name already taken under owner
    "auth_failed",        # 401 / 403
    "network_failed",     # transport error
    "unknown",
)

PUSH_FAILURE_RECOVERY: dict[str, str] = {
    "auth_failed": "GitHub 令牌无效或权限不足。请在「设置 → GitHub」中重新连接账号后重试。",
    "network_failed": "无法连接 GitHub。请检查网络连接后重试。",
    "non_fast_forward": "远程分支包含本地没有的提交。请先拉取（fetch + rebase）后再推送，或确认要强制覆盖。",
    "remote_exists": "远程 'origin' 已存在。请先移除旧远程或直接使用现有远程。",
    "unknown": "推送失败。请查看详细错误并稍后重试。",
}

CREATE_REPO_FAILURE_RECOVERY: dict[str, str] = {
    "name_exists": "该名称的仓库已存在。请换一个仓库名，或删除已有仓库后重试。",
    "auth_failed": "GitHub 令牌无效或权限不足。请重新连接账号后重试。",
    "network_failed": "无法连接 GitHub。请检查网络连接后重试。",
    "unknown": "创建仓库失败。请查看详细错误并稍后重试。",
}

# Substring markers used by ``classify_push_error``.
_AUTH_MARKERS = (
    "authentication failed",
    "could not read username",
    "repository not found",
    "remote: invalid username or password",
    "bad credentials",
    "permission denied",
    "403",
    "401",
)
_NETWORK_MARKERS = (
    "could not resolve host",
    "failed to connect",
    "connection refused",
    "network is unreachable",
    "operation timed out",
    "nodename nor servname",
    "timeout",
    "temporary failure in name resolution",
    "fatal: unable to access",
)
_NON_FF_MARKERS = (
    "non-fast-forward",
    "fetch first",
    "updates were rejected because the tip",
    "rejected",
)


@dataclass
class PushFailure:
    kind: str
    reason: str
    recovery: str


@dataclass
class CreateRepoFailure:
    kind: str
    reason: str
    recovery: str


@dataclass
class PushResult:
    ok: bool
    remote_url: Optional[str] = None
    failure: Optional[PushFailure] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "remote_url": self.remote_url,
            "failure": (
                {
                    "kind": self.failure.kind,
                    "reason": self.failure.reason,
                    "recovery": self.failure.recovery,
                }
                if self.failure
                else None
            ),
        }


def classify_push_error(stderr: str, returncode: int = 1) -> PushFailure:
    """Map raw git push stderr to one of the five required failure kinds."""
    text = (stderr or "").lower()
    if "already exists" in text and "origin" in text:
        return PushFailure(
            "remote_exists",
            "远程 'origin' 已存在（remote origin already exists）。",
            PUSH_FAILURE_RECOVERY["remote_exists"],
        )
    # Network errors are checked before auth because a DNS/timeout failure can
    # otherwise be misread via the generic "fatal: unable to access" string.
    if any(marker in text for marker in _NETWORK_MARKERS):
        return PushFailure(
            "network_failed",
            "推送失败：无法连接 GitHub 服务器。",
            PUSH_FAILURE_RECOVERY["network_failed"],
        )
    if any(marker in text for marker in _AUTH_MARKERS):
        return PushFailure(
            "auth_failed",
            "推送被拒绝：GitHub 令牌无效或权限不足。",
            PUSH_FAILURE_RECOVERY["auth_failed"],
        )
    if any(marker in text for marker in _NON_FF_MARKERS):
        return PushFailure(
            "non_fast_forward",
            "推送被拒绝：远程分支包含本地没有的提交（non-fast-forward）。",
            PUSH_FAILURE_RECOVERY["non_fast_forward"],
        )
    return PushFailure(
        "unknown",
        f"推送失败（exit={returncode}）。",
        PUSH_FAILURE_RECOVERY["unknown"],
    )


def classify_create_repo_error(status: int, body: Any) -> CreateRepoFailure:
    """Map a GitHub create-repo HTTP response to a failure kind."""
    message = ""
    if isinstance(body, dict):
        message = str(body.get("message") or body.get("errors") or "")
    if status == 422 or "name already exists" in message.lower():
        return CreateRepoFailure(
            "name_exists",
            "仓库名已存在（GitHub: name already exists）。",
            CREATE_REPO_FAILURE_RECOVERY["name_exists"],
        )
    if status in (401, 403):
        return CreateRepoFailure(
            "auth_failed",
            "创建仓库被拒绝：令牌无效或权限不足。",
            CREATE_REPO_FAILURE_RECOVERY["auth_failed"],
        )
    if status == 0:
        return CreateRepoFailure(
            "network_failed",
            "创建仓库失败：无法连接 GitHub。",
            CREATE_REPO_FAILURE_RECOVERY["network_failed"],
        )
    return CreateRepoFailure(
        "unknown",
        f"创建仓库失败（HTTP {status}）。",
        CREATE_REPO_FAILURE_RECOVERY["unknown"],
    )


class GitOps:
    """Thin, testable wrapper around the ``git`` CLI for one workspace."""

    def __init__(self, workspace: str, git_bin: str = DEFAULT_GIT_BIN) -> None:
        self.workspace = workspace
        self.git_bin = git_bin

    # --- low-level runner -----------------------------------------------------

    def _run(self, *args: str, check: bool = True, capture: bool = True) -> tuple[int, str, str]:
        cmd = [self.git_bin, "-C", self.workspace, *args]
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
            stderr=subprocess.PIPE if capture else subprocess.DEVNULL,
            text=True,
        )
        if check and proc.returncode != 0:
            raise RuntimeError(proc.stderr or proc.stdout or f"git {args[0]} failed")
        return proc.returncode, proc.stdout, proc.stderr

    # --- repo state -----------------------------------------------------------

    def is_repo(self) -> bool:
        code, out, _ = self._run("rev-parse", "--is-inside-work-tree", check=False)
        return code == 0 and out.strip() == "true"

    def _has_commits(self) -> bool:
        code, _, _ = self._run("rev-parse", "--verify", "--quiet", "HEAD", check=False)
        return code == 0

    def current_branch(self) -> Optional[str]:
        if not self.is_repo():
            return None
        _, out, _ = self._run("rev-parse", "--abbrev-ref", "HEAD", check=False)
        branch = out.strip()
        return branch or None

    # --- init / first commit (3.5 #3) ----------------------------------------

    def ensure_gitignore(self, entries: tuple[str, ...] = DEFAULT_GITIGNORE_ENTRIES) -> None:
        path = os.path.join(self.workspace, ".gitignore")
        existing: str = ""
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as handle:
                existing = handle.read()
        lines = [line.strip() for line in existing.splitlines()]
        additions = [e for e in entries if e not in lines]
        if not additions:
            return
        prefix = "" if (not existing or existing.endswith("\n")) else "\n"
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(f"{existing}{prefix}{'\n'.join(additions)}\n")

    def init(
        self,
        main_branch: str = DEFAULT_MAIN_BRANCH,
        *,
        commit_initial: bool = True,
        author_name: str = KYROZEN_AUTHOR_NAME,
        author_email: KYROZEN_AUTHOR_EMAIL = KYROZEN_AUTHOR_EMAIL,  # type: ignore[assignment]
        gitignore_entries: tuple[str, ...] = DEFAULT_GITIGNORE_ENTRIES,
    ) -> dict[str, Any]:
        """Initialize the repo on ``main`` with a ``.gitignore`` and, when the
        workspace already contains real project content, an initial commit."""
        if not self.is_repo():
            self._run("init", "--initial-branch", main_branch)
        self.ensure_gitignore(gitignore_entries)
        # Only set the local identity when missing so we never trample a user's.
        _, name, _ = self._run("config", "user.name", check=False)
        _, email, _ = self._run("config", "user.email", check=False)
        if not name.strip():
            self._run("config", "user.name", author_name)
        if not email.strip():
            self._run("config", "user.email", author_email)
        committed = False
        if commit_initial and not self._has_commits():
            self.add_all()
            staged = self._staged_files()
            if staged:
                self._run("commit", "-m", "chore: initial Kyrozen project commit")
                committed = True
        return {
            "success": True,
            "branch": self.current_branch(),
            "initial_commit": committed,
        }

    # --- staging / commit -----------------------------------------------------

    def _porcelain(self) -> list[str]:
        _, out, _ = self._run("status", "--porcelain", check=False)
        return [line for line in out.splitlines() if line]

    def _staged_files(self) -> list[str]:
        return [line[3:] for line in self._porcelain() if line and line[0] in "AMRD" and line[0] != " "]

    def add_all(self) -> None:
        self._run("add", "-A")

    def commit(
        self,
        message: str,
        author_name: str = KYROZEN_AUTHOR_NAME,
        author_email: KYROZEN_AUTHOR_EMAIL = KYROZEN_AUTHOR_EMAIL,  # type: ignore[assignment]
    ) -> dict[str, Any]:
        if not self.is_repo():
            return {"success": False, "error": "工作区不是 Git 仓库，请先初始化"}
        before = self._has_commits()
        self.add_all()
        if not self._staged_files() and before:
            # Nothing new to commit.
            return {"success": True, "committed": False, "branch": self.current_branch()}
        self._run(
            "-c", f"user.name={author_name}",
            "-c", f"user.email={author_email}",
            "commit", "-m", message,
        )
        return {"success": True, "committed": True, "branch": self.current_branch()}

    # --- status / history (3.5 #7) -------------------------------------------

    def status(self) -> dict[str, Any]:
        if not self.is_repo():
            return {"success": True, "is_repo": False}
        branch = self.current_branch()
        ahead = behind = 0
        _, upstream, _ = self._run(
            "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}", check=False
        )
        upstream = upstream.strip()
        if upstream:
            code_a, out_a, _ = self._run("rev-list", "--count", f"{upstream}..HEAD", check=False)
            code_b, out_b, _ = self._run("rev-list", "--count", f"HEAD..{upstream}", check=False)
            ahead = int(out_a.strip()) if code_a == 0 and out_a.strip().isdigit() else 0
            behind = int(out_b.strip()) if code_b == 0 and out_b.strip().isdigit() else 0
        modified: list[str] = []
        untracked: list[str] = []
        staged: list[str] = []
        for line in self._porcelain():
            if line.startswith("??"):
                untracked.append(line[3:])
            else:
                if len(line) > 0 and line[0] in "AMRD" and line[0] != " ":
                    staged.append(line[3:])
                if len(line) > 1 and line[1] in "MD":
                    modified.append(line[3:])
        return {
            "success": True,
            "is_repo": True,
            "branch": branch,
            "ahead": ahead,
            "behind": behind,
            "modified": modified,
            "untracked": untracked,
            "staged": staged,
        }

    def recent_commits(self, limit: int = 5) -> list[dict[str, str]]:
        if not self.is_repo():
            return []
        _, out, _ = self._run(
            "log", f"-n{limit}", "--date=short",
            "--pretty=format:%H%x1f%an%x1f%ad%x1f%s",
            check=False,
        )
        commits: list[dict[str, str]] = []
        for line in out.splitlines():
            parts = line.split("\x1f")
            if len(parts) == 4:
                commits.append(
                    {"hash": parts[0], "author": parts[1], "date": parts[2], "message": parts[3]}
                )
        return commits

    # --- remote ---------------------------------------------------------------

    def remote_url(self) -> Optional[str]:
        _, out, _ = self._run("remote", "get-url", "origin", check=False)
        return out.strip() or None

    def set_origin(self, url: str) -> dict[str, Any]:
        if not self.is_repo():
            return {"success": False, "error": "工作区不是 Git 仓库"}
        try:
            self._run("remote", "set-url", "origin", url)
        except RuntimeError:
            self._run("remote", "add", "origin", url)
        return {"success": True, "remote_url": self.remote_url()}

    # --- push (3.5 #5 / #6) ---------------------------------------------------

    def push(
        self,
        token: Optional[str] = None,
        set_upstream: bool = True,
        branch: Optional[str] = None,
    ) -> PushResult:
        if not self.is_repo():
            return PushResult(ok=False, failure=PushFailure("unknown", "工作区不是 Git 仓库", PUSH_FAILURE_RECOVERY["unknown"]))
        branch = branch or self.current_branch() or DEFAULT_MAIN_BRANCH
        args: list[str] = []
        if token:
            # One-shot header supplied on the command line only; never persisted.
            authorization = base64.b64encode(f"x-access-token:{token}".encode("utf-8")).decode("ascii")
            args += ["-c", f"http.extraHeader=Authorization: Basic {authorization}"]
        args += ["push"]
        if set_upstream:
            args += ["--set-upstream", "origin", branch]
        else:
            args += ["origin", branch]
        code, _, stderr = self._run(*args, check=False)
        if code != 0:
            return PushResult(ok=False, failure=classify_push_error(stderr, code))
        return PushResult(ok=True, remote_url=self.remote_url())


def scan_for_secrets(token: str, workspace: str) -> list[str]:
    """Return workspace-relative paths that contain ``token``.

    A clean implementation must return ``[]`` — the token must never be written
    to ``.git/config``, the remote URL, logs, or any project file (3.5 #5).
    """
    if not token:
        return []
    hits: list[str] = []
    git_config = os.path.join(workspace, ".git", "config")
    if os.path.exists(git_config):
        with open(git_config, "r", encoding="utf-8", errors="ignore") as handle:
            if token in handle.read():
                hits.append(os.path.relpath(git_config, workspace))
    for root, dirs, files in os.walk(workspace):
        # Never descend into the git internals.
        dirs[:] = [d for d in dirs if d != ".git"]
        for name in files:
            path = os.path.join(root, name)
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                    content = handle.read()
            except OSError:
                continue
            if token in content:
                hits.append(os.path.relpath(path, workspace))
    return hits
