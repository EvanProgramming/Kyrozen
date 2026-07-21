"""Memory interface for Kyrozen Core.

Phase 1 provides a save/query/update/delete abstraction with an in-memory
implementation. Future phases can add ChromaDB / vector-backed storage.
"""

from __future__ import annotations

import threading
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any


@dataclass
class MemoryRecord:
    """A single memory record."""

    id: str
    category: str  # user, project, knowledge, failure
    content: str
    metadata: dict[str, Any]
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MemoryInterface(ABC):
    """Abstract memory interface."""

    @abstractmethod
    def save(self, category: str, content: str, **metadata: Any) -> MemoryRecord:
        """Save a memory and return the created record."""
        ...

    @abstractmethod
    def query(self, category: str | None = None, query: str | None = None, limit: int = 10, **filters: Any) -> list[MemoryRecord]:
        """Query memories by category, keyword, and optional metadata filters."""
        ...

    @abstractmethod
    def update(self, record_id: str, content: str, **metadata: Any) -> MemoryRecord | None:
        """Update an existing memory."""
        ...

    @abstractmethod
    def delete(self, record_id: str) -> bool:
        """Delete a memory by id."""
        ...


class InMemoryMemory(MemoryInterface):
    """Simple in-memory memory implementation with keyword matching."""

    def __init__(self) -> None:
        self._records: dict[str, MemoryRecord] = {}
        self._lock = threading.Lock()

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
        return record

    def query(self, category: str | None = None, query: str | None = None, limit: int = 10, **filters: Any) -> list[MemoryRecord]:
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
            return record

    def delete(self, record_id: str) -> bool:
        with self._lock:
            if record_id in self._records:
                del self._records[record_id]
                return True
            return False
