"""Permission system for Kyrozen Core.

Distinguishes low-risk and high-risk operations.
- strict mode: high-risk operations require explicit confirmation.
- permissive mode: all operations are allowed (useful for testing).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


HIGH_RISK_TOOLS = {
    "file_write": ["write"],
    "terminal": ["execute"],
    "git": ["add", "commit", "push", "pull"],
}


@dataclass
class PermissionDecision:
    allowed: bool
    reason: str
    requires_confirmation: bool


class PermissionManager:
    """Decides whether a tool action is allowed under the current mode."""

    def __init__(self, mode: str = "strict") -> None:
        self.mode = mode

    def is_high_risk(self, tool: str, action: str) -> bool:
        actions = HIGH_RISK_TOOLS.get(tool, [])
        return action in actions or "*" in actions

    def check(self, tool: str, action: str, parameters: dict[str, Any] | None = None) -> PermissionDecision:
        if self.mode == "permissive":
            return PermissionDecision(allowed=True, reason="permissive mode", requires_confirmation=False)

        if self.is_high_risk(tool, action):
            return PermissionDecision(
                allowed=False,
                reason=f"High-risk action '{tool}.{action}' requires user confirmation in strict mode",
                requires_confirmation=True,
            )
        return PermissionDecision(allowed=True, reason="low-risk action", requires_confirmation=False)

    def confirm(self, tool: str, action: str, parameters: dict[str, Any] | None = None) -> PermissionDecision:
        """User explicitly confirmed the action."""
        return PermissionDecision(
            allowed=True,
            reason=f"User confirmed high-risk action '{tool}.{action}'",
            requires_confirmation=False,
        )
