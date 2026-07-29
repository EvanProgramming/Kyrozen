"""Startup schema preflight for the desktop / task tables.

The desktop client requires two schema objects that are introduced by
``migrations/002_add_desktop_client_support.sql``:

* ``tasks.assigned_client_id`` column
* ``desktop_clients`` table

Before this migration existed, the production server started fine but the
*first* chat message failed with ``PGRST204: Could not find the
'assigned_client_id' column`` -- a terrible first-run experience (P0-02).

This module lets the server refuse to start (or warn, in dev) when the schema
is missing, so the failure surfaces at deploy time instead of at user request.
"""

from __future__ import annotations

import os
from typing import Any


class SchemaError(RuntimeError):
    """Raised when required schema objects are missing."""

    def __init__(self, missing: list[str]) -> None:
        self.missing = missing
        items = ", ".join(missing)
        super().__init__(
            "数据库缺少桌面客户端所需的结构（已阻止服务启动）："
            f"{items}。请先执行迁移脚本：python scripts/apply_migrations.py "
            "(需设置 KYROZEN_POSTGRES_DSN 为 Supabase 连接池地址)，"
            "或在本地开发时设置 KYROZEN_ALLOW_MISSING_SCHEMA=1 跳过本检查。"
        )


def _is_missing_column_error(exc: Exception) -> bool:
    msg = str(exc)
    code = getattr(exc, "code", "") or ""
    return (
        "PGRST204" in code
        or "PGRST204" in msg
        or "assigned_client_id" in msg
        or "could not find" in msg.lower()
    )


def _is_missing_table_error(exc: Exception) -> bool:
    msg = str(exc)
    code = getattr(exc, "code", "") or ""
    return (
        "PGRST106" in code
        or "PGRST106" in msg
        or "does not exist" in msg.lower()
        or "relation" in msg.lower()
        and "desktop_clients" in msg
    )


def _column_present(client: Any, table: str, column: str) -> bool:
    """Return True if the column is queryable, False if explicitly missing.

    Any other error (e.g. network) is re-raised so the caller knows the
    verification itself failed.
    """
    try:
        client.table(table).select(column).limit(1).execute()
        return True
    except Exception as exc:  # noqa: BLE001 - we need to inspect the cause
        if _is_missing_column_error(exc):
            return False
        raise


def _table_present(client: Any, table: str) -> bool:
    try:
        client.table(table).select("id").limit(1).execute()
        return True
    except Exception as exc:  # noqa: BLE001
        if _is_missing_table_error(exc):
            return False
        raise


def verify_desktop_schema(config: Any, client: Any | None = None) -> None:
    """Verify the desktop schema; raise :class:`SchemaError` if anything is missing.

    Only applies to ``supabase`` / ``postgres`` backends. For ``sqlite`` (local
    dev) it is a no-op. ``client`` may be injected for testing.
    """
    backend = getattr(config, "db_backend", "")
    if backend not in ("supabase", "postgres"):
        return

    if client is None:
        supabase_url = getattr(config, "supabase_url", "")
        service_key = getattr(config, "supabase_service_role_key", "")
        if not supabase_url or not service_key:
            # Cannot verify; let startup proceed (caller may still warn).
            return
        from supabase import create_client

        client = create_client(supabase_url, service_key)

    missing: list[str] = []
    if not _column_present(client, "tasks", "assigned_client_id"):
        missing.append("tasks.assigned_client_id")
    if not _table_present(client, "desktop_clients"):
        missing.append("desktop_clients")

    if missing:
        raise SchemaError(missing)
