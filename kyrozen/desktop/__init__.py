"""Desktop client support for Kyrozen.

This module manages connections to local Electron desktop clients, including
authentication, task routing, and WebSocket communication.
"""

from .auth import DesktopTokenManager, verify_desktop_token
from .cloud_proxy import CloudProxyModelProvider
from .manager import DesktopClientManager
from .models import DesktopClient
from .quota import QuotaManager, QuotaStatus

__all__ = [
    "CloudProxyModelProvider",
    "DesktopClient",
    "DesktopClientManager",
    "DesktopTokenManager",
    "QuotaManager",
    "QuotaStatus",
    "verify_desktop_token",
]
