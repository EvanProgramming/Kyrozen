"""Database-backed repository for Kyrozen Phase 9 learning memory."""

from __future__ import annotations

import json
from typing import Any

from kyrozen.auth.context import get_current_user_id
from kyrozen.project.db import KyrozenDatabase
from kyrozen.project.supabase_db import SupabaseDatabase

from .models import (
    FailureKnowledge,
    LearningRecord,
    Suggestion,
    SuccessKnowledge,
)


class LearningRepository:
    """Persists learning records, failures, successes, and suggestions to the database.

    The repository reads the current user id from the request context. If no user
    is present, operations that require ownership will fail.
    """

    def __init__(self, db: KyrozenDatabase | SupabaseDatabase) -> None:
        self.db = db

    def _user_id(self) -> str:
        user_id = get_current_user_id()
        if not user_id:
            raise RuntimeError("LearningRepository requires an authenticated user context")
        return user_id

    # ------------------------------------------------------------------
    # Learning records
    # ------------------------------------------------------------------
    def save_record(self, record: LearningRecord) -> None:
        data = record.to_dict()
        data["user_id"] = self._user_id()
        self.db.save_learning_record(data)

    def list_records(
        self,
        source_project_id: str | None = None,
        memory_type: str | None = None,
        limit: int = 100,
    ) -> list[LearningRecord]:
        rows = self.db.list_learning_records(
            user_id=self._user_id(),
            source_project_id=source_project_id,
            memory_type=memory_type,
            limit=limit,
        )
        return [LearningRecord.from_dict(r) for r in rows]

    def get_record(self, record_id: str) -> LearningRecord | None:
        row = self.db.get_learning_record(record_id, self._user_id())
        if row is None:
            return None
        return LearningRecord.from_dict(row)

    def delete_record(self, record_id: str) -> bool:
        return self.db.delete_learning_record(record_id, self._user_id())

    # ------------------------------------------------------------------
    # Failure knowledge
    # ------------------------------------------------------------------
    def save_failure(self, failure: FailureKnowledge) -> None:
        data = failure.to_dict()
        data["user_id"] = self._user_id()
        self.db.save_failure_knowledge(data)

    def list_failures(
        self,
        source_project_id: str | None = None,
        limit: int = 100,
    ) -> list[FailureKnowledge]:
        rows = self.db.list_failure_knowledge(
            user_id=self._user_id(),
            source_project_id=source_project_id,
            limit=limit,
        )
        return [FailureKnowledge.from_dict(r) for r in rows]

    def get_failure(self, failure_id: str) -> FailureKnowledge | None:
        row = self.db.get_failure_knowledge(failure_id, self._user_id())
        if row is None:
            return None
        return FailureKnowledge.from_dict(row)

    def delete_failure(self, failure_id: str) -> bool:
        return self.db.delete_failure_knowledge(failure_id, self._user_id())

    # ------------------------------------------------------------------
    # Success knowledge
    # ------------------------------------------------------------------
    def save_success(self, success: SuccessKnowledge) -> None:
        data = success.to_dict()
        data["user_id"] = self._user_id()
        self.db.save_success_knowledge(data)

    def list_successes(
        self,
        source_project_id: str | None = None,
        limit: int = 100,
    ) -> list[SuccessKnowledge]:
        rows = self.db.list_success_knowledge(
            user_id=self._user_id(),
            source_project_id=source_project_id,
            limit=limit,
        )
        return [SuccessKnowledge.from_dict(r) for r in rows]

    def get_success(self, success_id: str) -> SuccessKnowledge | None:
        row = self.db.get_success_knowledge(success_id, self._user_id())
        if row is None:
            return None
        return SuccessKnowledge.from_dict(row)

    def delete_success(self, success_id: str) -> bool:
        return self.db.delete_success_knowledge(success_id, self._user_id())

    # ------------------------------------------------------------------
    # Suggestions
    # ------------------------------------------------------------------
    def save_suggestion(self, suggestion: Suggestion) -> None:
        data = suggestion.to_dict()
        data["user_id"] = self._user_id()
        self.db.save_suggestion(data)

    def list_suggestions(
        self,
        source_project_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[Suggestion]:
        rows = self.db.list_suggestions(
            user_id=self._user_id(),
            source_project_id=source_project_id,
            status=status,
            limit=limit,
        )
        return [Suggestion.from_dict(r) for r in rows]

    def get_suggestion(self, suggestion_id: str) -> Suggestion | None:
        row = self.db.get_suggestion(suggestion_id, self._user_id())
        if row is None:
            return None
        return Suggestion.from_dict(row)

    def update_suggestion_status(self, suggestion_id: str, status: str) -> bool:
        return self.db.update_suggestion_status(suggestion_id, self._user_id(), status)

    def delete_suggestion(self, suggestion_id: str) -> bool:
        return self.db.delete_suggestion(suggestion_id, self._user_id())

    # ------------------------------------------------------------------
    # Convenience queries used by the suggestion generator
    # ------------------------------------------------------------------
    def query_cross_project_memory(
        self,
        query_text: str,
        memory_type: str,
        scope: str = "user",
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Return matching learning records as plain dicts for suggestion generation."""
        if memory_type == "validated_failure":
            rows = self.db.list_failure_knowledge(user_id=self._user_id(), limit=limit * 2)
            items = [FailureKnowledge.from_dict(r).to_dict() for r in rows]
        elif memory_type == "validated_success":
            rows = self.db.list_success_knowledge(user_id=self._user_id(), limit=limit * 2)
            items = [SuccessKnowledge.from_dict(r).to_dict() for r in rows]
        else:
            rows = self.db.list_learning_records(
                user_id=self._user_id(),
                memory_type=memory_type,
                limit=limit * 2,
            )
            items = [LearningRecord.from_dict(r).to_dict() for r in rows]

        query_lower = query_text.lower()
        filtered = [item for item in items if query_lower in json.dumps(item, ensure_ascii=False).lower()]
        return filtered[:limit]
