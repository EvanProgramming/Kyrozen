"""Terminal / shell execution tool for Kyrozen Core."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any

from ._paths import _get_allowed_root, _resolve_safe_path
from .base import Tool, ToolParameter, ToolResult, ToolSchema


_MAX_TIMEOUT_SECONDS = 300

_BLOCKED_PATTERNS = [
    # Destructive file operations
    r"\brm\s+(-rf?|-\s*rf?)\s",
    r"\brm\s+.*-r",
    r"^\s*rm\s+-rf",
    r"\brm\s+-rf\b",
    r"\bmkfs\.\w+",
    r">\s*/dev/sd",
    r":\(\)\s*\{\s*:\s*\|\s*:\s*&",
    r"\bdel\s+/[fs](?:\s+/[sq])?\s+\S:\\\\",
    r"\brd\s+/[sq]\s+\S:\\\\",
    r"\brmdir\s+/[sq]\s+\S:\\\\",
    r"\bformat\s+\w:",
    r"\bdiskpart\b",
    r"\bdeltree\b",
    # Privilege escalation / remote execution
    r"\bsudo\b",
    r"\bsu\b",
    r"\bssh\b",
    r"\brsync\b",
    r"\bscp\b",
    r"\bsftp\b",
    r"\bnc\b",
    r"\bnetcat\b",
    r"\bpython\s+-m\s+http\.server",
    r"\bphp\s+-S\b",
    # Pipe-to-shell downloads
    r"wget\s+.*\|\s*sh\s*$",
    r"curl\s+.*\|\s*sh\s*$",
    r"wget\s+.*\|\s*bash\s*$",
    r"curl\s+.*\|\s*bash\s*$",
    # Windows destructive / system commands
    r"\bwmic\s+process\s+where.*delete\b",
    r"\btaskkill\s+/f\s+/im\s+(?:svchost|winlogon|csrss|lsass|smss|wininit|services)\b",
    r"\breg\s+delete\s+HKLM",
    r"\bicacls\s+\S+\s+/deny",
    # Common backshell indicators
    r"bash\s+-i\b",
    r"sh\s+-i\b",
    r"/bin/bash\s+-i\b",
    r"/bin/sh\s+-i\b",
    r"\bpython\s+.*socket.*subprocess\b",
]
_BLOCKED_RE = re.compile("|".join(_BLOCKED_PATTERNS), re.IGNORECASE)


def _is_dangerous(cmd: str) -> bool:
    return bool(_BLOCKED_RE.search(cmd))


_PATH_ESCAPE_RE = re.compile(r"(^|/|\s)\.\.(\.|/|\s|$)")


def _contains_path_escape(cmd: str) -> bool:
    """Detect attempts to walk out of the working directory with '..'."""
    return bool(_PATH_ESCAPE_RE.search(cmd))


class TerminalTool(Tool):
    """Execute a shell command within the project workspace."""

    name = "terminal"
    description = "Execute a shell command and return stdout/stderr."
    schema = ToolSchema(
        name=name,
        description=description,
        actions={
            "execute": [
                ToolParameter("command", "string", "Shell command to execute", required=True),
                ToolParameter("timeout", "integer", "Timeout in seconds (default: 60, max: 300)", required=False),
                ToolParameter("cwd", "string", "Working directory (default: project or workspace root)", required=False),
            ]
        },
    )

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        cmd = parameters.get("command", "").strip()
        if not cmd:
            return ToolResult(success=False, data=None, error="No command provided")
        if _is_dangerous(cmd):
            return ToolResult(success=False, data=None, error="Command blocked for safety")
        if _contains_path_escape(cmd):
            return ToolResult(success=False, data=None, error="Command contains path escape '..' and is not allowed")

        timeout = parameters.get("timeout", 60) or 60
        timeout = min(int(timeout), _MAX_TIMEOUT_SECONDS)

        allowed_root = _get_allowed_root(parameters)
        raw_cwd = parameters.get("cwd", ".") or "."
        cwd_path, error = _resolve_safe_path(raw_cwd, allowed_root)
        if cwd_path is None:
            return ToolResult(success=False, data=None, error=error)
        if not cwd_path.is_dir():
            return ToolResult(success=False, data=None, error=f"Working directory does not exist: {cwd_path}")

        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(cwd_path),
                env={**os.environ, "HOME": str(allowed_root), "USERPROFILE": str(allowed_root)},
            )
            output = (result.stdout or "") + (("\nstderr:\n" + result.stderr) if result.stderr else "")
            if result.returncode != 0:
                return ToolResult(
                    success=False,
                    data={"exit_code": result.returncode, "output": output.strip()},
                    error=f"Command exited with code {result.returncode}",
                )
            return ToolResult(success=True, data={"output": output.strip() or "(no output)"})
        except subprocess.TimeoutExpired:
            return ToolResult(success=False, data=None, error=f"Command timed out after {timeout}s")
        except Exception as e:
            return ToolResult(success=False, data=None, error=f"Error executing command: {e}")
