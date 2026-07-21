"""Scoped memory implementations for Kyrozen Phase 2.

Provides file-backed memory and project-scoped wrappers.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .interface import MemoryInterface, MemoryRecord


class JsonFileMemory(MemoryInterface):
    """File-backed memory that persists records to a JSON file."""

    def __init__(self, file_path: str) -> None:
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self._records: dict[str, MemoryRecord] = {}
        self._lock = threading.Lock()
        self._load()

    def _load(self) -> None:
        if not self.file_path.exists():
            return
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for record_id, record_data in data.items():
                self._records[record_id] = MemoryRecord(**record_data)
        except Exception:
            pass

    def _save(self) -> None:
        try:
            data = {rid: record.to_dict() for rid, record in self._records.items()}
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def save(self, category: str, content: str, **metadata: Any) -> MemoryRecord:
        record = MemoryRecord(
            id=f"mem_{uuid.uuid4().hex[:8]}",
            category=category,
            content=content,
            metadata=metadata,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        with self._lock:
            self._records[record.id] = record
            self._save()
        return record

    def query(
        self,
        category: str | None = None,
        query: str | None = None,
        limit: int = 10,
        **filters: Any,
    ) -> list[MemoryRecord]:
        with self._lock:
            records = list(self._records.values())
        if category:
            records = [r for r in records if r.category == category]
        for key, value in filters.items():
            records = [r for r in records if r.metadata.get(key) == value]
        if query:
            query_lower = query.lower()
            records = [r for r in records if query_lower in r.content.lower()]
        records.sort(key=lambda r: r.timestamp, reverse=True)
        return records[:limit]

    def update(self, record_id: str, content: str, **metadata: Any) -> MemoryRecord | None:
        with self._lock:
            record = self._records.get(record_id)
            if record is None:
                return None
            record.content = content
            record.metadata.update(metadata)
            record.timestamp = datetime.now(timezone.utc).isoformat()
            self._save()
            return record

    def delete(self, record_id: str) -> bool:
        with self._lock:
            if record_id in self._records:
                del self._records[record_id]
                self._save()
                return True
            return False


class ProjectMemory:
    """Convenience wrapper for project-scoped memory."""

    def __init__(self, project_id: str, backend: MemoryInterface) -> None:
        self.project_id = project_id
        self.backend = backend

    def save(self, category: str, content: str, **metadata: Any) -> MemoryRecord:
        metadata["project_id"] = self.project_id
        return self.backend.save(category, content, **metadata)

    def query(
        self,
        category: str | None = None,
        query: str | None = None,
        limit: int = 10,
        **filters: Any,
    ) -> list[MemoryRecord]:
        filters["project_id"] = self.project_id
        return self.backend.query(category=category, query=query, limit=limit, **filters)

    def update(self, record_id: str, content: str, **metadata: Any) -> MemoryRecord | None:
        metadata["project_id"] = self.project_id
        return self.backend.update(record_id, content, **metadata)

    def delete(self, record_id: str) -> bool:
        return self.backend.delete(record_id)
