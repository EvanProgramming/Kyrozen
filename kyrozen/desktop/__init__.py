"""Desktop client support for Kyrozen.

This module manages connections to local Electron desktop clients, including
authentication, task routing, and WebSocket communication.
"""

from .auth import DesktopTokenManager, verify_desktop_token
from .manager import DesktopClientManager
from .models import DesktopClient

__all__ = [
    "DesktopClient",
    "DesktopClientManager",
    "DesktopTokenManager",
    "verify_desktop_token",
]
