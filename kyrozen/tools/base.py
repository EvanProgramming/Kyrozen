"""Base types for the Kyrozen tool system.

Every tool must expose:
- name
- description
- parameter schema
- validation
- execution
- result
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolParameter:
    """Definition of one tool parameter."""

    name: str
    param_type: str  # string, integer, boolean
    description: str
    required: bool = True


@dataclass
class ToolSchema:
    """Schema describing a tool and its supported actions."""

    name: str
    description: str
    actions: dict[str, list[ToolParameter]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "actions": {
                action: [
                    {"name": p.name, "type": p.param_type, "description": p.description, "required": p.required}
                    for p in params
                ]
                for action, params in self.actions.items()
            },
        }


@dataclass
class ToolResult:
    """Result of a tool execution."""

    success: bool
    data: Any
    error: str = ""
    execution_time_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
        }


class Tool(ABC):
    """Base class for all Kyrozen tools."""

    name: str = ""
    description: str = ""
    schema: ToolSchema = ToolSchema(name="", description="")

    def validate(self, action: str, parameters: dict[str, Any]) -> tuple[bool, str]:
        """Validate parameters against the schema for the given action."""
        if action not in self.schema.actions:
            return False, f"Action '{action}' is not supported by tool '{self.name}'"
        required_params = {p.name for p in self.schema.actions[action] if p.required}
        missing = required_params - set(parameters.keys())
        if missing:
            return False, f"Missing required parameters: {', '.join(sorted(missing))}"
        return True, ""

    def execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        """Validate and execute the tool action, measuring execution time."""
        valid, error = self.validate(action, parameters)
        if not valid:
            return ToolResult(success=False, data=None, error=error)
        start = time.time()
        try:
            result = self._execute(action, parameters)
        except Exception as e:
            result = ToolResult(success=False, data=None, error=f"{type(e).__name__}: {e}")
        result.execution_time_ms = (time.time() - start) * 1000
        return result

    @abstractmethod
    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        """Concrete implementation. Must return a ToolResult."""
        ...
