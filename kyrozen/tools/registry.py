"""Tool registry for Kyrozen Core."""

from __future__ import annotations

from typing import Any

from .base import Tool, ToolResult, ToolSchema
from .file_tools import FileReadTool, FileWriteTool, ListDirTool, FindFilesTool
from .terminal_tools import TerminalTool
from .git_tools import GitTool


class ToolRegistry:
    """Registry of available tools."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        return sorted(self._tools.keys())

    def list_schemas(self) -> list[dict[str, Any]]:
        return [tool.schema.to_dict() for tool in self._tools.values()]

    def execute(self, name: str, action: str, parameters: dict[str, Any]) -> ToolResult:
        tool = self.get(name)
        if tool is None:
            return ToolResult(success=False, data=None, error=f"Tool '{name}' not found")
        return tool.execute(action, parameters)


def get_default_registry() -> ToolRegistry:
    """Return a registry with Phase 1 tools pre-registered."""
    registry = ToolRegistry()
    registry.register(FileReadTool())
    registry.register(FileWriteTool())
    registry.register(ListDirTool())
    registry.register(FindFilesTool())
    registry.register(TerminalTool())
    registry.register(GitTool())
    return registry
