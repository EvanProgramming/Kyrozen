"""Data models for desktop client management."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class DesktopClient:
    """A connected desktop client instance."""

    user_id: str
    client_id: str = field(default_factory=lambda: f"client_{uuid.uuid4().hex[:12]}")
    device_name: str = "Unknown Device"
    client_version: str = ""
    platform: str = ""
    current_project_id: str | None = None
    online: bool = True
    last_active_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    websocket: Any | None = field(default=None, repr=False)

    def touch(self) -> None:
        self.last_active_at = datetime.now(timezone.utc).isoformat()
        self.online = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "client_id": self.client_id,
            "user_id": self.user_id,
            "device_name": self.device_name,
            "client_version": self.client_version,
            "platform": self.platform,
            "current_project_id": self.current_project_id,
            "online": self.online,
            "last_active_at": self.last_active_at,
            "created_at": self.created_at,
        }
