"""Tool exposing the 3.5 local Git + GitHub workflow to the agent.

Mirrors ``InteractionTool``: every action takes ``workspace_root`` and delegates
to :mod:`kyrozen.core.git_ops` / :mod:`kyrozen.core.github`. The GitHub token is
injected at construction time (``github_token``) and is **never** passed through
tool parameters, so it cannot leak into tool JSON, operation logs, or diagnostics
(3.5 requirement #5).
"""

from __future__ import annotations

from typing import Any, Optional

from kyrozen.core import github as gh_mod
from kyrozen.core import git_ops as git_mod
from kyrozen.tools.base import Tool, ToolParameter, ToolResult, ToolSchema


def _ws(params: dict[str, Any]) -> str:
    ws = str(params.get("workspace_root") or "")
    if not ws:
        raise ValueError("workspace_root is required")
    return ws


class GitGithubTool(Tool):
    name = "git_github"
    description = "本地 Git 与 GitHub 工作流：初始化仓库、提交、推送、创建私有/公开仓库、查询账号与提交历史。"

    schema = ToolSchema(
        name=name,
        description=description,
        actions={
            "init": [
                ToolParameter("workspace_root", "string", "项目工作区根目录", required=True),
                ToolParameter("main_branch", "string", "主分支名（默认 main）", required=False),
                ToolParameter("commit_initial", "boolean", "无提交时创建首个提交（默认 true）", required=False),
            ],
            "status": [
                ToolParameter("workspace_root", "string", "项目工作区根目录", required=True),
            ],
            "recent_commits": [
                ToolParameter("workspace_root", "string", "项目工作区根目录", required=True),
                ToolParameter("limit", "integer", "返回条数（默认 5）", required=False),
            ],
            "remote": [
                ToolParameter("workspace_root", "string", "项目工作区根目录", required=True),
            ],
            "commit": [
                ToolParameter("workspace_root", "string", "项目工作区根目录", required=True),
                ToolParameter("message", "string", "提交信息", required=True),
            ],
            "push": [
                ToolParameter("workspace_root", "string", "项目工作区根目录", required=True),
                ToolParameter("message", "string", "可选：先提交再推送", required=False),
                ToolParameter("branch", "string", "分支名（默认当前分支）", required=False),
                ToolParameter("set_upstream", "boolean", "设置 upstream（默认 true）", required=False),
            ],
            "create_repo": [
                ToolParameter("owner", "string", "仓库所有者登录名（建库前确认）", required=True),
                ToolParameter("name", "string", "仓库名", required=True),
                ToolParameter("private", "boolean", "是否私有仓库（默认 true）", required=False),
                ToolParameter("description", "string", "仓库描述（可选）", required=False),
            ],
            "github_user": [
                ToolParameter("scopes", "string", "可选：已知 scope 列表 JSON", required=False),
            ],
        },
    )

    def __init__(self, github_token: Optional[str] = None, git_bin: str = git_mod.DEFAULT_GIT_BIN) -> None:
        super().__init__()
        self.github_token = github_token
        self.git_bin = git_bin
        self.github = gh_mod.GitHubClient()

    def _ops(self, params: dict[str, Any]) -> git_mod.GitOps:
        return git_mod.GitOps(_ws(params), git_bin=self.git_bin)

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        try:
            if action == "init":
                return self._init(parameters)
            if action == "status":
                return self._status(parameters)
            if action == "recent_commits":
                return self._recent_commits(parameters)
            if action == "remote":
                return self._remote(parameters)
            if action == "commit":
                return self._commit(parameters)
            if action == "push":
                return self._push(parameters)
            if action == "create_repo":
                return self._create_repo(parameters)
            if action == "github_user":
                return self._github_user(parameters)
        except Exception as exc:  # defensive
            return ToolResult(success=False, data=None, error=f"{type(exc).__name__}: {exc}")
        return ToolResult(success=False, data=None, error=f"Unsupported action '{action}'")

    # -- actions -------------------------------------------------------------

    def _init(self, params: dict[str, Any]) -> ToolResult:
        ops = self._ops(params)
        main_branch = str(params.get("main_branch") or git_mod.DEFAULT_MAIN_BRANCH)
        commit_initial = params.get("commit_initial", True)
        if isinstance(commit_initial, str):
            commit_initial = commit_initial.lower() != "false"
        result = ops.init(main_branch=main_branch, commit_initial=bool(commit_initial))
        return ToolResult(success=result["success"], data=result)

    def _status(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data=self._ops(params).status())

    def _recent_commits(self, params: dict[str, Any]) -> ToolResult:
        limit = params.get("limit", 5)
        try:
            limit = int(limit)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            limit = 5
        return ToolResult(success=True, data={"commits": self._ops(params).recent_commits(limit)})

    def _remote(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={"remote_url": self._ops(params).remote_url()})

    def _commit(self, params: dict[str, Any]) -> ToolResult:
        message = str(params.get("message") or "")
        if not message:
            return ToolResult(success=False, data=None, error="message is required")
        result = self._ops(params).commit(message)
        return ToolResult(success=result["success"], data=result)

    def _push(self, params: dict[str, Any]) -> ToolResult:
        ops = self._ops(params)
        message = params.get("message")
        if message:
            commit_result = ops.commit(str(message))
            if not commit_result["success"]:
                return ToolResult(success=False, data=commit_result)
        set_upstream = params.get("set_upstream", True)
        if isinstance(set_upstream, str):
            set_upstream = set_upstream.lower() != "false"
        result = ops.push(
            token=self.github_token,
            set_upstream=bool(set_upstream),
            branch=str(params["branch"]) if params.get("branch") else None,
        )
        return ToolResult(success=result.ok, data=result.to_dict())

    def _create_repo(self, params: dict[str, Any]) -> ToolResult:
        if not self.github_token:
            return ToolResult(success=False, data=None, error="未配置 GitHub 令牌")
        owner = str(params.get("owner") or "")
        name = str(params.get("name") or "")
        if not owner or not name:
            return ToolResult(success=False, data=None, error="owner 和 name 必填")
        private = params.get("private", True)
        if isinstance(private, str):
            private = private.lower() != "false"
        result = self.github.create_repo(
            self.github_token, owner, name, bool(private), description=str(params.get("description") or "")
        )
        return ToolResult(success=result.ok, data=result.to_dict())

    def _github_user(self, params: dict[str, Any]) -> ToolResult:
        if not self.github_token:
            return ToolResult(success=False, data=None, error="未配置 GitHub 令牌")
        scopes = None
        raw = params.get("scopes")
        if isinstance(raw, str) and raw.strip():
            try:
                scopes = __import__("json").loads(raw)
            except Exception:
                scopes = None
        user = self.github.get_user(self.github_token, scopes=scopes)
        return ToolResult(success=True, data=user.to_dict())
