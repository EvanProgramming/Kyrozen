"""Supabase PostgreSQL persistence adapter for Kyrozen."""

from __future__ import annotations

import logging
from typing import Any

from supabase import create_client

from kyrozen.config import KyrozenConfig

from .project import Artifact, Decision, Project


logger = logging.getLogger(__name__)


class SupabaseDatabase:
    """Supabase PostgreSQL database adapter matching the SQLite KyrozenDatabase interface."""

    def __init__(self, config: KyrozenConfig) -> None:
        if not config.supabase_url or not config.supabase_service_role_key:
            raise ValueError("Supabase URL and service role key are required")
        self.config = config
        self.client = create_client(config.supabase_url, config.supabase_service_role_key)

    def _execute_upsert(self, table: str, data: dict[str, Any]) -> None:
        """Run an upsert and tolerate transient network errors."""
        try:
            self.client.table(table).upsert(data).execute()
        except Exception as exc:
            if self._is_missing_table_error(exc):
                raise
            if self._is_network_error(exc):
                logger.warning(
                    "Failed to upsert %s to Supabase due to network error: %s", table, exc
                )
                return
            raise

    def _execute_insert(self, table: str, data: dict[str, Any]) -> None:
        """Run an insert and tolerate transient network errors."""
        try:
            self.client.table(table).insert(data).execute()
        except Exception as exc:
            if self._is_missing_table_error(exc):
                raise
            if self._is_network_error(exc):
                logger.warning(
                    "Failed to insert %s to Supabase due to network error: %s", table, exc
                )
                return
            raise

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------
    def save_project(self, project: Project) -> None:
        data = {
            "id": project.id,
            "user_id": str(project.user_id) if project.user_id else None,
            "name": project.name,
            "description": project.description,
            "goal": project.goal,
            "status": project.status,
            "current_stage": project.current_stage,
            "next_steps": project.next_steps,
            "blocked_reason": getattr(project, "blocked_reason", None),
            "progress": getattr(project, "progress", 0),
            "risks": project.risks if project.risks else [],
            "created_at": project.created_at,
            "updated_at": project.updated_at,
        }
        self._execute_upsert("projects", data)

    def get_project(self, project_id: str) -> Project | None:
        try:
            response = self.client.table("projects").select("*").eq("id", project_id).execute()
        except Exception as exc:
            if self._is_missing_table_error(exc):
                raise
            return None
        rows = getattr(response, "data", [])
        if not rows:
            return None
        return self._row_to_project(rows[0])

    def list_projects(self, user_id: str | None = None) -> list[Project]:
        try:
            query = self.client.table("projects").select("*")
            if user_id:
                query = query.eq("user_id", user_id)
            response = query.order("updated_at", desc=True).execute()
        except Exception as exc:
            if self._is_missing_table_error(exc):
                raise
            return []
        rows = getattr(response, "data", [])
        return [self._row_to_project(row) for row in rows]

    def delete_project(self, project_id: str) -> bool:
        try:
            response = self.client.table("projects").delete().eq("id", project_id).execute()
        except Exception:
            return False
        rows = getattr(response, "data", [])
        return len(rows) > 0

    def _row_to_project(self, row: dict[str, Any]) -> Project:
        return Project.from_dict({
            "id": row["id"],
            "user_id": row.get("user_id") or "",
            "name": row["name"],
            "description": row.get("description") or "",
            "goal": row.get("goal") or "",
            "status": row["status"],
            "current_stage": row["current_stage"],
            "next_steps": row.get("next_steps") or "",
            "blocked_reason": row.get("blocked_reason") or "",
            "progress": row.get("progress", 0) or 0,
            "risks": row.get("risks") or [],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        })

    # ------------------------------------------------------------------
    # Tasks
    # ------------------------------------------------------------------
    def save_task(self, task: Any) -> None:
        from kyrozen.core.task import Task

        if not isinstance(task, Task):
            raise TypeError("Expected Task instance")
        user_id = self._user_id_for_project(getattr(task, "project_id", None))
        data = {
            "id": task.id,
            "user_id": user_id,
            "project_id": getattr(task, "project_id", None),
            "title": task.title,
            "description": task.description,
            "status": task.status,
            "steps": [s.to_dict() for s in task.steps] if task.steps else [],
            "result": task.result,
            "errors": task.errors if task.errors else [],
            "created_at": task.created_at,
            "updated_at": task.updated_at,
        }
        self._execute_upsert("tasks", data)

    def get_task(self, task_id: str) -> Any | None:
        from kyrozen.core.task import Task

        try:
            response = self.client.table("tasks").select("*").eq("id", task_id).execute()
        except Exception as exc:
            if self._is_missing_table_error(exc):
                raise
            return None
        rows = getattr(response, "data", [])
        if not rows:
            return None
        return self._row_to_task(rows[0], Task)

    def list_tasks(self, project_id: str | None = None) -> list[Any]:
        from kyrozen.core.task import Task

        try:
            query = self.client.table("tasks").select("*")
            if project_id:
                query = query.eq("project_id", project_id)
            response = query.order("updated_at", desc=True).execute()
        except Exception as exc:
            if self._is_missing_table_error(exc):
                raise
            return []
        rows = getattr(response, "data", [])
        return [self._row_to_task(row, Task) for row in rows]

    def _row_to_task(self, row: dict[str, Any], TaskCls: type) -> Any:
        from kyrozen.core.task import TaskStep

        task = TaskCls(
            title=row["title"],
            description=row.get("description") or "",
            task_id=row["id"],
            status=row["status"],
        )
        task.project_id = row.get("project_id")
        task.created_at = row["created_at"]
        task.updated_at = row["updated_at"]
        task.result = row.get("result")
        task.errors = row.get("errors") or []
        for step_data in row.get("steps") or []:
            task.steps.append(TaskStep(**step_data))
        return task

    # ------------------------------------------------------------------
    # Decisions
    # ------------------------------------------------------------------
    def save_decision(self, decision: Decision) -> None:
        user_id = self._user_id_for_project(decision.project_id)
        data = {
            "id": decision.id,
            "user_id": user_id,
            "project_id": decision.project_id,
            "decision": decision.decision,
            "reason": decision.reason,
            "alternatives": decision.alternatives if decision.alternatives else [],
            "rejected_reasons": decision.rejected_reasons if decision.rejected_reasons else {},
            "source": decision.source,
            "timestamp": decision.timestamp,
        }
        self._execute_upsert("decisions", data)

    def get_decision(self, decision_id: str) -> Decision | None:
        try:
            response = self.client.table("decisions").select("*").eq("id", decision_id).execute()
        except Exception as exc:
            if self._is_missing_table_error(exc):
                raise
            return None
        rows = getattr(response, "data", [])
        if not rows:
            return None
        return self._row_to_decision(rows[0])

    def list_decisions(self, project_id: str) -> list[Decision]:
        try:
            response = (
                self.client.table("decisions")
                .select("*")
                .eq("project_id", project_id)
                .order("timestamp", desc=True)
                .execute()
            )
        except Exception as exc:
            if self._is_missing_table_error(exc):
                raise
            return []
        rows = getattr(response, "data", [])
        return [self._row_to_decision(row) for row in rows]

    def _row_to_decision(self, row: dict[str, Any]) -> Decision:
        return Decision.from_dict({
            "id": row["id"],
            "project_id": row["project_id"],
            "decision": row["decision"],
            "reason": row.get("reason") or "",
            "alternatives": row.get("alternatives") or [],
            "rejected_reasons": row.get("rejected_reasons") or {},
            "source": row.get("source") or "agent",
            "timestamp": row["timestamp"],
        })

    # ------------------------------------------------------------------
    # Artifacts
    # ------------------------------------------------------------------
    def save_artifact(self, artifact: Artifact) -> None:
        user_id = self._user_id_for_project(artifact.project_id)
        data = {
            "id": artifact.id,
            "user_id": user_id,
            "project_id": artifact.project_id,
            "type": artifact.type,
            "title": artifact.title,
            "content": artifact.content,
            "version": artifact.version,
            "change_reason": artifact.change_reason,
            "created_at": artifact.created_at,
            "updated_at": artifact.updated_at,
        }
        self._execute_upsert("artifacts", data)

    def get_artifact(self, artifact_id: str) -> Artifact | None:
        try:
            response = self.client.table("artifacts").select("*").eq("id", artifact_id).execute()
        except Exception as exc:
            if self._is_missing_table_error(exc):
                raise
            return None
        rows = getattr(response, "data", [])
        if not rows:
            return None
        return self._row_to_artifact(rows[0])

    def list_artifacts(self, project_id: str) -> list[Artifact]:
        try:
            response = (
                self.client.table("artifacts")
                .select("*")
                .eq("project_id", project_id)
                .order("updated_at", desc=True)
                .execute()
            )
        except Exception as exc:
            if self._is_missing_table_error(exc):
                raise
            return []
        rows = getattr(response, "data", [])
        return [self._row_to_artifact(row) for row in rows]

    def _row_to_artifact(self, row: dict[str, Any]) -> Artifact:
        return Artifact.from_dict({
            "id": row["id"],
            "project_id": row["project_id"],
            "type": row["type"],
            "title": row["title"],
            "content": row.get("content") or "",
            "version": row.get("version", 1),
            "change_reason": row.get("change_reason") or "",
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        })

    # ------------------------------------------------------------------
    # Feedback
    # ------------------------------------------------------------------
    def save_feedback(self, feedback: dict[str, Any]) -> None:
        data = {
            "id": feedback["id"],
            "user_id": str(feedback["user_id"]) if feedback.get("user_id") else None,
            "project_id": feedback.get("project_id"),
            "type": feedback["type"],
            "description": feedback["description"],
            "priority": feedback.get("priority", "medium"),
            "status": feedback.get("status", "open"),
            "metadata": feedback.get("metadata") or {},
            "created_at": feedback.get("created_at"),
            "updated_at": feedback.get("updated_at"),
        }
        self._execute_upsert("user_feedback", data)

    def list_feedback(self, user_id: str | None = None) -> list[dict[str, Any]]:
        try:
            query = self.client.table("user_feedback").select("*")
            if user_id:
                query = query.eq("user_id", user_id)
            response = query.order("created_at", desc=True).execute()
        except Exception as exc:
            if self._is_missing_table_error(exc):
                raise
            return []
        return list(getattr(response, "data", []))

    # ------------------------------------------------------------------
    # Analytics events
    # ------------------------------------------------------------------
    def save_event(self, event: dict[str, Any]) -> None:
        data = {
            "user_id": str(event["user_id"]) if event.get("user_id") else None,
            "project_id": event.get("project_id"),
            "event_type": event["event_type"],
            "payload": event.get("payload") or {},
            "session_id": event.get("session_id"),
            "created_at": event.get("created_at"),
        }
        self._execute_insert("events", data)

    def list_events(
        self,
        user_id: str | None = None,
        project_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        try:
            query = self.client.table("events").select("*")
            if user_id:
                query = query.eq("user_id", user_id)
            if project_id:
                query = query.eq("project_id", project_id)
            response = query.order("created_at", desc=True).limit(limit).execute()
        except Exception as exc:
            if self._is_missing_table_error(exc):
                raise
            return []
        return list(getattr(response, "data", []))

    # ------------------------------------------------------------------
    # Error monitoring
    # ------------------------------------------------------------------
    def save_error(self, error: dict[str, Any]) -> None:
        data = {
            "user_id": str(error["user_id"]) if error.get("user_id") else None,
            "project_id": error.get("project_id"),
            "endpoint": error.get("endpoint"),
            "method": error.get("method"),
            "error_type": error.get("error_type"),
            "message": error.get("message"),
            "stack": error.get("stack"),
            "payload": error.get("payload"),
            "created_at": error.get("created_at"),
        }
        self._execute_insert("error_logs", data)

    def list_errors(self, limit: int = 100) -> list[dict[str, Any]]:
        try:
            response = (
                self.client.table("error_logs")
                .select("*")
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
        except Exception as exc:
            if self._is_missing_table_error(exc):
                raise
            return []
        return list(getattr(response, "data", []))

    # ------------------------------------------------------------------
    # Learning memory
    # ------------------------------------------------------------------
    def save_learning_record(self, record: dict[str, Any]) -> None:
        data = {
            "id": record["id"],
            "user_id": str(record["user_id"]) if record.get("user_id") else None,
            "source_project_id": record.get("source_project_id"),
            "memory": record["memory"],
            "memory_type": record["memory_type"],
            "source": record.get("source"),
            "confidence": record.get("confidence", "low"),
            "verification_status": record.get("verification_status", "unverified"),
            "scope": record.get("scope", "private"),
            "tags": record.get("tags") or [],
            "created_at": record.get("created_at"),
            "updated_at": record.get("updated_at"),
        }
        self._execute_upsert("learning_records", data)

    def list_learning_records(
        self,
        user_id: str,
        source_project_id: str | None = None,
        memory_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        try:
            query = self.client.table("learning_records").select("*").eq("user_id", user_id)
            if source_project_id:
                query = query.eq("source_project_id", source_project_id)
            if memory_type:
                query = query.eq("memory_type", memory_type)
            response = query.order("created_at", desc=True).limit(limit).execute()
        except Exception as exc:
            if self._is_missing_table_error(exc):
                raise
            return []
        return list(getattr(response, "data", []))

    def get_learning_record(self, record_id: str, user_id: str) -> dict[str, Any] | None:
        try:
            response = (
                self.client.table("learning_records")
                .select("*")
                .eq("id", record_id)
                .eq("user_id", user_id)
                .execute()
            )
        except Exception as exc:
            if self._is_missing_table_error(exc):
                raise
            return None
        rows = getattr(response, "data", [])
        return rows[0] if rows else None

    def delete_learning_record(self, record_id: str, user_id: str) -> bool:
        try:
            response = (
                self.client.table("learning_records")
                .delete()
                .eq("id", record_id)
                .eq("user_id", user_id)
                .execute()
            )
        except Exception:
            return False
        rows = getattr(response, "data", [])
        return len(rows) > 0

    def save_failure_knowledge(self, failure: dict[str, Any]) -> None:
        data = {
            "id": failure["id"],
            "user_id": str(failure["user_id"]) if failure.get("user_id") else None,
            "source_project_id": failure.get("source_project_id"),
            "problem": failure["problem"],
            "cause": failure.get("cause"),
            "solution": failure.get("solution"),
            "affected_scope": failure.get("affected_scope"),
            "verification": failure.get("verification"),
            "confidence": failure.get("confidence", "medium"),
            "verification_status": failure.get("verification_status", "unverified"),
            "created_at": failure.get("created_at"),
            "updated_at": failure.get("updated_at"),
        }
        self._execute_upsert("failure_knowledge", data)

    def list_failure_knowledge(
        self,
        user_id: str,
        source_project_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        try:
            query = self.client.table("failure_knowledge").select("*").eq("user_id", user_id)
            if source_project_id:
                query = query.eq("source_project_id", source_project_id)
            response = query.order("created_at", desc=True).limit(limit).execute()
        except Exception as exc:
            if self._is_missing_table_error(exc):
                raise
            return []
        return list(getattr(response, "data", []))

    def get_failure_knowledge(self, failure_id: str, user_id: str) -> dict[str, Any] | None:
        try:
            response = (
                self.client.table("failure_knowledge")
                .select("*")
                .eq("id", failure_id)
                .eq("user_id", user_id)
                .execute()
            )
        except Exception as exc:
            if self._is_missing_table_error(exc):
                raise
            return None
        rows = getattr(response, "data", [])
        return rows[0] if rows else None

    def delete_failure_knowledge(self, failure_id: str, user_id: str) -> bool:
        try:
            response = (
                self.client.table("failure_knowledge")
                .delete()
                .eq("id", failure_id)
                .eq("user_id", user_id)
                .execute()
            )
        except Exception:
            return False
        rows = getattr(response, "data", [])
        return len(rows) > 0

    def save_success_knowledge(self, success: dict[str, Any]) -> None:
        data = {
            "id": success["id"],
            "user_id": str(success["user_id"]) if success.get("user_id") else None,
            "source_project_id": success.get("source_project_id"),
            "goal": success.get("goal"),
            "solution": success["solution"],
            "conditions": success.get("conditions") or [],
            "result": success.get("result"),
            "confidence": success.get("confidence", "medium"),
            "verification_status": success.get("verification_status", "unverified"),
            "created_at": success.get("created_at"),
            "updated_at": success.get("updated_at"),
        }
        self._execute_upsert("success_knowledge", data)

    def list_success_knowledge(
        self,
        user_id: str,
        source_project_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        try:
            query = self.client.table("success_knowledge").select("*").eq("user_id", user_id)
            if source_project_id:
                query = query.eq("source_project_id", source_project_id)
            response = query.order("created_at", desc=True).limit(limit).execute()
        except Exception as exc:
            if self._is_missing_table_error(exc):
                raise
            return []
        return list(getattr(response, "data", []))

    def get_success_knowledge(self, success_id: str, user_id: str) -> dict[str, Any] | None:
        try:
            response = (
                self.client.table("success_knowledge")
                .select("*")
                .eq("id", success_id)
                .eq("user_id", user_id)
                .execute()
            )
        except Exception as exc:
            if self._is_missing_table_error(exc):
                raise
            return None
        rows = getattr(response, "data", [])
        return rows[0] if rows else None

    def delete_success_knowledge(self, success_id: str, user_id: str) -> bool:
        try:
            response = (
                self.client.table("success_knowledge")
                .delete()
                .eq("id", success_id)
                .eq("user_id", user_id)
                .execute()
            )
        except Exception:
            return False
        rows = getattr(response, "data", [])
        return len(rows) > 0

    def save_suggestion(self, suggestion: dict[str, Any]) -> None:
        data = {
            "id": suggestion["id"],
            "user_id": str(suggestion["user_id"]) if suggestion.get("user_id") else None,
            "source_project_id": suggestion["source_project_id"],
            "suggestion": suggestion["suggestion"],
            "reason": suggestion.get("reason"),
            "evidence": suggestion.get("evidence") or [],
            "impact": suggestion.get("impact"),
            "priority": suggestion.get("priority", "medium"),
            "status": suggestion.get("status", "new"),
            "category": suggestion.get("category"),
            "related_learning_ids": suggestion.get("related_learning_ids") or [],
            "created_at": suggestion.get("created_at"),
            "updated_at": suggestion.get("updated_at"),
        }
        self._execute_upsert("suggestions", data)

    def list_suggestions(
        self,
        user_id: str,
        source_project_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        try:
            query = self.client.table("suggestions").select("*").eq("user_id", user_id)
            if source_project_id:
                query = query.eq("source_project_id", source_project_id)
            if status:
                query = query.eq("status", status)
            response = query.order("created_at", desc=True).limit(limit).execute()
        except Exception as exc:
            if self._is_missing_table_error(exc):
                raise
            return []
        return list(getattr(response, "data", []))

    def get_suggestion(self, suggestion_id: str, user_id: str) -> dict[str, Any] | None:
        try:
            response = (
                self.client.table("suggestions")
                .select("*")
                .eq("id", suggestion_id)
                .eq("user_id", user_id)
                .execute()
            )
        except Exception as exc:
            if self._is_missing_table_error(exc):
                raise
            return None
        rows = getattr(response, "data", [])
        return rows[0] if rows else None

    def update_suggestion_status(self, suggestion_id: str, user_id: str, status: str) -> bool:
        try:
            response = (
                self.client.table("suggestions")
                .update({"status": status})
                .eq("id", suggestion_id)
                .eq("user_id", user_id)
                .execute()
            )
        except Exception:
            return False
        rows = getattr(response, "data", [])
        return len(rows) > 0

    def delete_suggestion(self, suggestion_id: str, user_id: str) -> bool:
        try:
            response = (
                self.client.table("suggestions")
                .delete()
                .eq("id", suggestion_id)
                .eq("user_id", user_id)
                .execute()
            )
        except Exception:
            return False
        rows = getattr(response, "data", [])
        return len(rows) > 0

    # ------------------------------------------------------------------
    # Chat messages
    # ------------------------------------------------------------------
    def save_chat_message(self, message: dict[str, Any]) -> None:
        data = {
            "id": message["id"],
            "user_id": message["user_id"],
            "project_id": message["project_id"],
            "role": message["role"],
            "content": message["content"],
            "metadata": message.get("metadata") or {},
            "created_at": message.get("created_at"),
        }
        try:
            self.client.table("chat_messages").upsert(data).execute()
        except Exception as exc:
            import logging
            logger = logging.getLogger(__name__)
            if self._is_missing_table_error(exc):
                logger.warning(
                    "chat_messages table does not exist in Supabase; chat history will not be persisted. "
                    "Run the provided migration to enable cloud chat history."
                )
                return
            # Network/SSL errors should not break the chat endpoint.
            if self._is_network_error(exc):
                logger.warning(
                    "Failed to persist chat message to Supabase due to network error: %s. "
                    "Chat history will not be saved for this message.",
                    exc,
                )
                return
            raise

    def list_chat_messages(
        self,
        project_id: str,
        user_id: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        try:
            query = self.client.table("chat_messages").select("*").eq("project_id", project_id)
            if user_id:
                query = query.eq("user_id", user_id)
            response = query.order("created_at", desc=False).limit(limit).execute()
        except Exception as exc:
            if self._is_missing_table_error(exc):
                return []
            return []
        return list(getattr(response, "data", []))

    def delete_chat_messages(self, project_id: str, user_id: str) -> bool:
        try:
            response = (
                self.client.table("chat_messages")
                .delete()
                .eq("project_id", project_id)
                .eq("user_id", user_id)
                .execute()
            )
        except Exception:
            return False
        rows = getattr(response, "data", [])
        return len(rows) > 0

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------
    def _user_id_for_project(self, project_id: str | None) -> str | None:
        if not project_id:
            return None
        try:
            response = self.client.table("projects").select("user_id").eq("id", project_id).execute()
        except Exception:
            return None
        rows = getattr(response, "data", [])
        if rows:
            return rows[0].get("user_id")
        return None

    def _is_missing_table_error(self, exc: Exception) -> bool:
        message = str(exc).lower()
        return (
            "does not exist" in message
            or "relation" in message
            or "could not find the table" in message
            or "schema cache" in message
        )

    def _is_network_error(self, exc: Exception) -> bool:
        message = str(exc).lower()
        return (
            "ssl" in message
            or "connecterror" in message
            or "timeout" in message
            or "network" in message
            or "unreachable" in message
            or "connection" in message
            or "disconnected" in message
        )

    def close(self) -> None:
        pass
