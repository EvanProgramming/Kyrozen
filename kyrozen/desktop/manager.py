"""In-memory manager for connected desktop clients."""

from __future__ import annotations

import threading
from typing import Any

from kyrozen.logs import get_logger

from .models import DesktopClient


class DesktopClientManager:
    """Track online desktop clients and route tasks to them."""

    def __init__(self) -> None:
        self._clients: dict[str, DesktopClient] = {}
        self._lock = threading.Lock()
        self._logger = get_logger("INFO")

    def register(
        self,
        user_id: str,
        device_name: str = "Unknown Device",
        client_version: str = "",
        platform: str = "",
        current_project_id: str | None = None,
        websocket: Any | None = None,
    ) -> DesktopClient:
        """Register a new desktop client connection."""
        client = DesktopClient(
            user_id=user_id,
            device_name=device_name,
            client_version=client_version,
            platform=platform,
            current_project_id=current_project_id,
            websocket=websocket,
        )
        with self._lock:
            # Mark any existing clients for this user as offline when a new one
            # connects from the same device name, but keep them in the registry.
            self._clients[client.client_id] = client
        self._logger.info(f"Desktop client registered: {client.client_id} for user {user_id}")
        return client

    def unregister(self, client_id: str) -> None:
        """Mark a client as offline."""
        with self._lock:
            client = self._clients.get(client_id)
            if client:
                client.online = False
        self._logger.info(f"Desktop client unregistered: {client_id}")

    def get(self, client_id: str) -> DesktopClient | None:
        with self._lock:
            return self._clients.get(client_id)

    def list_for_user(self, user_id: str) -> list[DesktopClient]:
        """Return all clients for a user, most recently active first."""
        with self._lock:
            clients = [c for c in self._clients.values() if c.user_id == user_id]
        clients.sort(key=lambda c: c.last_active_at, reverse=True)
        return clients

    def list_online_for_user(self, user_id: str) -> list[DesktopClient]:
        """Return online clients for a user, most recently active first."""
        with self._lock:
            clients = [c for c in self._clients.values() if c.user_id == user_id and c.online]
        clients.sort(key=lambda c: c.last_active_at, reverse=True)
        return clients

    def pick_client_for_task(self, user_id: str, project_id: str | None = None) -> DesktopClient | None:
        """Pick the most appropriate online client for a task.

        Prefers clients currently looking at the target project, then falls back
        to the most recently active online client.
        """
        online = self.list_online_for_user(user_id)
        if not online:
            return None
        if project_id:
            for client in online:
                if client.current_project_id == project_id:
                    return client
        return online[0]

    async def send_to_client(self, client_id: str, message: dict[str, Any]) -> bool:
        """Send a JSON message to a specific client."""
        client = self.get(client_id)
        if client is None or client.websocket is None:
            return False
        try:
            await client.websocket.send_json(message)
            client.touch()
            return True
        except Exception as exc:
            self._logger.warning(f"Failed to send message to {client_id}: {exc}")
            self.unregister(client_id)
            return False

    async def broadcast_to_user(self, user_id: str, message: dict[str, Any]) -> None:
        """Send a message to all online clients for a user."""
        for client in self.list_online_for_user(user_id):
            await self.send_to_client(client.client_id, message)

    def update_project(self, client_id: str, project_id: str | None) -> None:
        """Update the currently active project for a client."""
        client = self.get(client_id)
        if client:
            client.current_project_id = project_id
            client.touch()

    def touch(self, client_id: str) -> None:
        client = self.get(client_id)
        if client:
            client.touch()
