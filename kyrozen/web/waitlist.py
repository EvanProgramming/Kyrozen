"""Lightweight waitlist storage backed by SQLite.

The waitlist is kept separate from the main application database so it works
regardless of whether the backend is configured to use SQLite, PostgreSQL, or
Supabase for project data.
"""

from __future__ import annotations

import re
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS waitlist (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    source TEXT,
    ip TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_waitlist_email ON waitlist(email);
CREATE INDEX IF NOT EXISTS idx_waitlist_created ON waitlist(created_at);
"""


class WaitlistStore:
    """Store and retrieve waitlist email addresses."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._lock = threading.Lock()
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(SCHEMA_SQL)

    def add(self, email: str, source: str | None = None, ip: str | None = None) -> dict[str, Any]:
        """Add an email to the waitlist.

        Returns a dict with ``success`` and either ``id`` or ``error``.
        """
        normalized = email.strip().lower()
        if not normalized or not EMAIL_REGEX.match(normalized):
            return {"success": False, "error": "请输入有效的邮箱地址"}

        entry_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            try:
                conn.execute(
                    "INSERT INTO waitlist (id, email, source, ip, created_at) VALUES (?, ?, ?, ?, ?)",
                    (entry_id, normalized, source or "website", ip, now),
                )
                return {"success": True, "id": entry_id}
            except sqlite3.IntegrityError:
                return {"success": False, "error": "该邮箱已在等待列表中"}

    def list_all(self, limit: int = 1000) -> list[dict[str, Any]]:
        """Return all waitlist entries, newest first."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM waitlist ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]
