"""Git tools for Kyrozen Core."""

from __future__ import annotations

import os
import subprocess
from typing import Any

from .base import Tool, ToolParameter, ToolResult, ToolSchema


class GitTool(Tool):
    """Execute git commands."""

    name = "git"
    description = "Run git commands in the current workspace."
    schema = ToolSchema(
        name=name,
        description=description,
        actions={
            "status": [ToolParameter("path", "string", "Repository path (default: current directory)", required=False)],
            "diff": [ToolParameter("path", "string", "Repository path (default: current directory)", required=False)],
            "log": [
                ToolParameter("path", "string", "Repository path (default: current directory)", required=False),
                ToolParameter("limit", "integer", "Number of commits to show", required=False),
            ],
            "add": [
                ToolParameter("path", "string", "Repository path (default: current directory)", required=False),
                ToolParameter("files", "string", "Files to stage (default: .)", required=False),
            ],
            "commit": [
                ToolParameter("path", "string", "Repository path (default: current directory)", required=False),
                ToolParameter("message", "string", "Commit message", required=True),
            ],
            "push": [ToolParameter("path", "string", "Repository path (default: current directory)", required=False)],
            "pull": [ToolParameter("path", "string", "Repository path (default: current directory)", required=False)],
        },
    )

    def _repo_path(self, parameters: dict[str, Any]) -> str:
        raw = parameters.get("path", ".") or "."
        path = os.path.expanduser(raw)
        if not os.path.isabs(path):
            path = os.path.abspath(path)
        return path

    def _run_git(self, repo_path: str, *args: str) -> ToolResult:
        cmd = ["git", "-C", repo_path, *args]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            output = (result.stdout or "").strip()
            error = (result.stderr or "").strip()
            if result.returncode != 0:
                return ToolResult(success=False, data={"output": output, "stderr": error}, error=f"Git failed: {error}")
            return ToolResult(success=True, data={"output": output or "(no output)"})
        except Exception as e:
            return ToolResult(success=False, data=None, error=f"Error running git: {e}")

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        repo_path = self._repo_path(parameters)
        if action == "status":
            return self._run_git(repo_path, "status")
        if action == "diff":
            return self._run_git(repo_path, "diff")
        if action == "log":
            limit = parameters.get("limit", 10) or 10
            return self._run_git(repo_path, "log", "--oneline", "--decorate", f"-{int(limit)}")
        if action == "add":
            files = parameters.get("files", ".") or "."
            return self._run_git(repo_path, "add", *files.split())
        if action == "commit":
            message = parameters.get("message", "")
            if not message:
                return ToolResult(success=False, data=None, error="Commit message is required")
            return self._run_git(repo_path, "commit", "-m", message)
        if action == "push":
            return self._run_git(repo_path, "push")
        if action == "pull":
            return self._run_git(repo_path, "pull")
        return ToolResult(success=False, data=None, error=f"Unknown git action: {action}")
