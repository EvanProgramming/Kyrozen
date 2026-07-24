"""Permission system for Kyrozen Core.

Distinguishes low-risk and high-risk operations.
- strict mode: high-risk operations require explicit confirmation each time.
- session_trust mode: like strict, but the user can choose to trust the current
  agent for the remainder of the session; subsequent matching high-risk actions
  skip confirmation while still being logged.
- full_trust mode: all operations are allowed; intended for power users who have
  explicitly opted in and recorded a Decision Record.
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
        if mode not in {"strict", "session_trust", "full_trust", "permissive"}:
            raise ValueError(f"Unsupported permission mode: {mode}")
        self.mode = mode
        self._session_trusted: set[str] = set()

    def is_high_risk(self, tool: str, action: str) -> bool:
        actions = HIGH_RISK_TOOLS.get(tool, [])
        return action in actions or "*" in actions

    def _key(self, tool: str, action: str) -> str:
        return f"{tool}.{action}"

    def check(self, tool: str, action: str, parameters: dict[str, Any] | None = None) -> PermissionDecision:
        if self.mode == "permissive":
            return PermissionDecision(allowed=True, reason="permissive mode", requires_confirmation=False)

        if self.mode == "full_trust":
            return PermissionDecision(
                allowed=True,
                reason="full trust mode: user previously opted in",
                requires_confirmation=False,
            )

        if self.is_high_risk(tool, action):
            if self._session_trusted and self._key(tool, action) in self._session_trusted:
                return PermissionDecision(
                    allowed=True,
                    reason=f"Session-trusted high-risk action '{tool}.{action}'",
                    requires_confirmation=False,
                )
            return PermissionDecision(
                allowed=False,
                reason=f"High-risk action '{tool}.{action}' requires user confirmation",
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

    def trust_for_session(self, tool: str, action: str) -> None:
        """Mark a high-risk action as trusted for the remainder of the session."""
        self._session_trusted.add(self._key(tool, action))

    def is_session_trusted(self, tool: str, action: str) -> bool:
        return self._key(tool, action) in self._session_trusted

    def reset_session_trust(self) -> None:
        """Clear all session-level trust grants."""
        self._session_trusted.clear()
