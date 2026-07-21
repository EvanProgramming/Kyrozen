"""Terminal / shell execution tool for Kyrozen Core."""

from __future__ import annotations

import re
import subprocess
from typing import Any

from .base import Tool, ToolParameter, ToolResult, ToolSchema


_BLOCKED_PATTERNS = [
    r"\brm\s+(-rf?|-\s*rf?)\s",
    r"\brm\s+.*-r",
    r"^\s*rm\s+-rf",
    r"\brm\s+-rf\b",
    r"\bmkfs\.\w+",
    r">\s*/dev/sd",
    r":\(\)\s*\{\s*:\s*\|\s*:\s*&",
    r"wget\s+.*\|\s*sh\s*$",
    r"curl\s+.*\|\s*sh\s*$",
    r"\bdel\s+/[fs](?:\s+/[sq])?\s+\S:\\\\",
    r"\brd\s+/[sq]\s+\S:\\\\",
    r"\brmdir\s+/[sq]\s+\S:\\\\",
    r"\bformat\s+\w:",
    r"\bdiskpart\b",
    r"\bwmic\s+process\s+where.*delete\b",
    r"\btaskkill\s+/f\s+/im\s+(?:svchost|winlogon|csrss|lsass|smss|wininit|services)\b",
    r"\breg\s+delete\s+HKLM",
    r"\bicacls\s+\S+\s+/deny",
    r"\bdeltree\b",
]
_BLOCKED_RE = re.compile("|".join(_BLOCKED_PATTERNS), re.IGNORECASE)


def _is_dangerous(cmd: str) -> bool:
    return bool(_BLOCKED_RE.search(cmd))


class TerminalTool(Tool):
    """Execute a shell command."""

    name = "terminal"
    description = "Execute a shell command and return stdout/stderr."
    schema = ToolSchema(
        name=name,
        description=description,
        actions={
            "execute": [
                ToolParameter("command", "string", "Shell command to execute", required=True),
                ToolParameter("timeout", "integer", "Timeout in seconds (default: 60)", required=False),
            ]
        },
    )

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        cmd = parameters.get("command", "").strip()
        if not cmd:
            return ToolResult(success=False, data=None, error="No command provided")
        if _is_dangerous(cmd):
            return ToolResult(success=False, data=None, error="Command blocked for safety")
        timeout = parameters.get("timeout", 60) or 60
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=int(timeout),
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
