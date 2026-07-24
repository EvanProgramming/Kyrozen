"""File system tools for Kyrozen Core."""

from __future__ import annotations

import glob
import os
from pathlib import Path
from typing import Any

from ._paths import _get_allowed_root, _resolve_safe_path
from .base import Tool, ToolParameter, ToolResult, ToolSchema


class FileReadTool(Tool):
    """Read file contents."""

    name = "file_read"
    description = "Read the contents of a file."
    schema = ToolSchema(
        name=name,
        description=description,
        actions={
            "read": [ToolParameter("path", "string", "Absolute or relative path to the file", required=True)]
        },
    )

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        raw_path = parameters.get("path", "")
        allowed_root = _get_allowed_root(parameters)
        path, error = _resolve_safe_path(raw_path, allowed_root, parameters.get("project_id"))
        if path is None:
            return ToolResult(success=False, data=None, error=error)
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            return ToolResult(success=True, data={"path": str(path), "content": content})
        except FileNotFoundError:
            return ToolResult(success=False, data=None, error=f"File not found: {path}")
        except Exception as e:
            return ToolResult(success=False, data=None, error=f"Error reading file: {e}")


class FileWriteTool(Tool):
    """Write content to a file."""

    name = "file_write"
    description = "Write content to a file, creating parent directories if needed."
    schema = ToolSchema(
        name=name,
        description=description,
        actions={
            "write": [
                ToolParameter("path", "string", "Absolute or relative path to the file", required=True),
                ToolParameter("content", "string", "Content to write", required=True),
            ]
        },
    )

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        raw_path = parameters.get("path", "")
        content = parameters.get("content", "")
        allowed_root = _get_allowed_root(parameters)
        path, error = _resolve_safe_path(raw_path, allowed_root, parameters.get("project_id"))
        if path is None:
            return ToolResult(success=False, data=None, error=error)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return ToolResult(success=True, data={"path": str(path), "characters_written": len(content)})
        except Exception as e:
            return ToolResult(success=False, data=None, error=f"Error writing file: {e}")


class ListDirTool(Tool):
    """List directory contents."""

    name = "list_dir"
    description = "List the contents of a directory."
    schema = ToolSchema(
        name=name,
        description=description,
        actions={
            "list": [ToolParameter("path", "string", "Directory path (default: current directory)", required=False)]
        },
    )

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        raw_path = parameters.get("path", ".") or "."
        allowed_root = _get_allowed_root(parameters)
        path, error = _resolve_safe_path(raw_path, allowed_root, parameters.get("project_id"))
        if path is None:
            return ToolResult(success=False, data=None, error=error)
        try:
            entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name))
            items = [{"name": p.name, "type": "file" if p.is_file() else "directory"} for p in entries]
            return ToolResult(success=True, data={"path": str(path), "entries": items})
        except Exception as e:
            return ToolResult(success=False, data=None, error=f"Error listing directory: {e}")


class FindFilesTool(Tool):
    """Find files matching a glob pattern."""

    name = "find_files"
    description = "Find files matching a glob pattern."
    schema = ToolSchema(
        name=name,
        description=description,
        actions={
            "find": [
                ToolParameter("pattern", "string", "Glob pattern (e.g. *.py)", required=True),
                ToolParameter("directory", "string", "Directory to search in (default: current directory)", required=False),
            ]
        },
    )

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        pattern = parameters.get("pattern", "")
        raw_directory = parameters.get("directory", ".") or "."
        allowed_root = _get_allowed_root(parameters)
        dir_path, error = _resolve_safe_path(raw_directory, allowed_root, parameters.get("project_id"))
        if dir_path is None:
            return ToolResult(success=False, data=None, error=error)
        try:
            # Ensure the glob stays inside the allowed directory by refusing
            # absolute patterns or patterns that walk upward.
            if Path(pattern).is_absolute() or ".." in Path(pattern).parts:
                return ToolResult(
                    success=False,
                    data=None,
                    error="Glob pattern must be relative and cannot contain '..'",
                )
            matches = sorted(glob.glob(str(dir_path / pattern), recursive=True))
            return ToolResult(success=True, data={"pattern": pattern, "directory": str(dir_path), "matches": matches})
        except Exception as e:
            return ToolResult(success=False, data=None, error=f"Error finding files: {e}")
