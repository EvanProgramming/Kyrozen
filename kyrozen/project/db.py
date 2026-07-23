"""SQLite persistence for the Kyrozen Project Workspace."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .project import Artifact, Decision, Project


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    name TEXT NOT NULL,
    description TEXT,
    goal TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    current_stage TEXT NOT NULL DEFAULT 'problem_discovery',
    next_steps TEXT,
    blocked_reason TEXT,
    progress INTEGER NOT NULL DEFAULT 0,
    risks TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    project_id TEXT,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    steps TEXT,
    result TEXT,
    errors TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS decisions (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    project_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    reason TEXT,
    alternatives TEXT,
    rejected_reasons TEXT,
    source TEXT,
    timestamp TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    project_id TEXT NOT NULL,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    change_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_decisions_project ON decisions(project_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_project ON artifacts(project_id);
CREATE INDEX IF NOT EXISTS idx_projects_user ON projects(user_id);
CREATE INDEX IF NOT EXISTS idx_tasks_user ON tasks(user_id);
CREATE INDEX IF NOT EXISTS idx_decisions_user ON decisions(user_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_user ON artifacts(user_id);

CREATE TABLE IF NOT EXISTS user_feedback (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
    type TEXT NOT NULL,
    description TEXT NOT NULL,
    priority TEXT DEFAULT 'medium',
    status TEXT DEFAULT 'open',
    metadata TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_feedback_user ON user_feedback(user_id);
CREATE INDEX IF NOT EXISTS idx_feedback_project ON user_feedback(project_id);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
    event_type TEXT NOT NULL,
    payload TEXT,
    session_id TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_user ON events(user_id);
CREATE INDEX IF NOT EXISTS idx_events_project ON events(project_id);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);

CREATE TABLE IF NOT EXISTS error_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    project_id TEXT,
    endpoint TEXT,
    method TEXT,
    error_type TEXT,
    message TEXT,
    stack TEXT,
    payload TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_error_logs_user ON error_logs(user_id);

CREATE TABLE IF NOT EXISTS learning_records (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    source_project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
    memory TEXT NOT NULL,
    memory_type TEXT NOT NULL,
    source TEXT,
    confidence TEXT NOT NULL DEFAULT 'low',
    verification_status TEXT NOT NULL DEFAULT 'unverified',
    scope TEXT NOT NULL DEFAULT 'private',
    tags TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_learning_records_user ON learning_records(user_id);
CREATE INDEX IF NOT EXISTS idx_learning_records_project ON learning_records(source_project_id);
CREATE INDEX IF NOT EXISTS idx_learning_records_type ON learning_records(memory_type);

CREATE TABLE IF NOT EXISTS failure_knowledge (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    source_project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
    problem TEXT NOT NULL,
    cause TEXT,
    solution TEXT,
    affected_scope TEXT,
    verification TEXT,
    confidence TEXT NOT NULL DEFAULT 'medium',
    verification_status TEXT NOT NULL DEFAULT 'unverified',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_failure_knowledge_user ON failure_knowledge(user_id);
CREATE INDEX IF NOT EXISTS idx_failure_knowledge_project ON failure_knowledge(source_project_id);

CREATE TABLE IF NOT EXISTS success_knowledge (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    source_project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
    goal TEXT,
    solution TEXT NOT NULL,
    conditions TEXT,
    result TEXT,
    confidence TEXT NOT NULL DEFAULT 'medium',
    verification_status TEXT NOT NULL DEFAULT 'unverified',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_success_knowledge_user ON success_knowledge(user_id);
CREATE INDEX IF NOT EXISTS idx_success_knowledge_project ON success_knowledge(source_project_id);

CREATE TABLE IF NOT EXISTS suggestions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    source_project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    suggestion TEXT NOT NULL,
    reason TEXT,
    evidence TEXT,
    impact TEXT,
    priority TEXT NOT NULL DEFAULT 'medium',
    status TEXT NOT NULL DEFAULT 'new',
    category TEXT,
    related_learning_ids TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_suggestions_user ON suggestions(user_id);
CREATE INDEX IF NOT EXISTS idx_suggestions_project ON suggestions(source_project_id);

CREATE TABLE IF NOT EXISTS chat_messages (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_messages_project ON chat_messages(project_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_user ON chat_messages(user_id);
"""


class KyrozenDatabase:
    """Thread-safe SQLite database for projects, tasks, decisions, and artifacts."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._lock = threading.Lock()
        self._ensure_dir()
        self._init_schema()

    def _ensure_dir(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(SCHEMA_SQL)

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------
    def save_project(self, project: Project) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO projects (id, user_id, name, description, goal, status, current_stage,
                                      next_steps, blocked_reason, progress, risks, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    user_id=excluded.user_id,
                    name=excluded.name,
                    description=excluded.description,
                    goal=excluded.goal,
                    status=excluded.status,
                    current_stage=excluded.current_stage,
                    next_steps=excluded.next_steps,
                    blocked_reason=excluded.blocked_reason,
                    progress=excluded.progress,
                    risks=excluded.risks,
                    updated_at=excluded.updated_at
                """,
                (
                    project.id,
                    getattr(project, "user_id", None),
                    project.name,
                    project.description,
                    project.goal,
                    project.status,
                    project.current_stage,
                    project.next_steps,
                    getattr(project, "blocked_reason", None),
                    getattr(project, "progress", 0),
                    json.dumps(project.risks, ensure_ascii=False),
                    project.created_at,
                    project.updated_at,
                ),
            )

    def get_project(self, project_id: str) -> Project | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM projects WHERE id = ?", (project_id,)
            ).fetchone()
        if row is None:
            return None
        return self._row_to_project(row)

    def list_projects(self, user_id: str | None = None) -> list[Project]:
        query = "SELECT * FROM projects"
        params: tuple[Any, ...] = ()
        if user_id:
            query += " WHERE user_id = ?"
            params = (user_id,)
        query += " ORDER BY updated_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_project(row) for row in rows]

    def delete_project(self, project_id: str) -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            return cur.rowcount > 0

    def _row_to_project(self, row: sqlite3.Row) -> Project:
        return Project.from_dict({
            "id": row["id"],
            "user_id": row["user_id"] or "",
            "name": row["name"],
            "description": row["description"] or "",
            "goal": row["goal"] or "",
            "status": row["status"],
            "current_stage": row["current_stage"],
            "next_steps": row["next_steps"] or "",
            "blocked_reason": row["blocked_reason"] or "",
            "progress": row["progress"] or 0,
            "risks": json.loads(row["risks"] or "[]"),
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
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO tasks (id, project_id, title, description, status, steps,
                                   result, errors, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    project_id=excluded.project_id,
                    title=excluded.title,
                    description=excluded.description,
                    status=excluded.status,
                    steps=excluded.steps,
                    result=excluded.result,
                    errors=excluded.errors,
                    updated_at=excluded.updated_at
                """,
                (
                    task.id,
                    getattr(task, "project_id", None),
                    task.title,
                    task.description,
                    task.status,
                    json.dumps([s.to_dict() for s in task.steps], ensure_ascii=False),
                    json.dumps(task.result, ensure_ascii=False) if task.result is not None else None,
                    json.dumps(task.errors, ensure_ascii=False),
                    task.created_at,
                    task.updated_at,
                ),
            )

    def get_task(self, task_id: str) -> Any | None:
        from kyrozen.core.task import Task
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_task(row, Task)

    def list_tasks(self, project_id: str | None = None) -> list[Any]:
        from kyrozen.core.task import Task
        query = "SELECT * FROM tasks"
        params: tuple[Any, ...] = ()
        if project_id:
            query += " WHERE project_id = ?"
            params = (project_id,)
        query += " ORDER BY updated_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_task(row, Task) for row in rows]

    def _row_to_task(self, row: sqlite3.Row, TaskCls: type) -> Any:
        from kyrozen.core.task import TaskStep
        task = TaskCls(
            title=row["title"],
            description=row["description"] or "",
            task_id=row["id"],
            status=row["status"],
        )
        task.project_id = row["project_id"]
        task.created_at = row["created_at"]
        task.updated_at = row["updated_at"]
        task.result = json.loads(row["result"]) if row["result"] else None
        task.errors = json.loads(row["errors"] or "[]")
        for step_data in json.loads(row["steps"] or "[]"):
            task.steps.append(TaskStep(**step_data))
        return task

    # ------------------------------------------------------------------
    # Decisions
    # ------------------------------------------------------------------
    def save_decision(self, decision: Decision) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO decisions (id, project_id, decision, reason, alternatives,
                                       rejected_reasons, source, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    decision=excluded.decision,
                    reason=excluded.reason,
                    alternatives=excluded.alternatives,
                    rejected_reasons=excluded.rejected_reasons,
                    source=excluded.source,
                    timestamp=excluded.timestamp
                """,
                (
                    decision.id,
                    decision.project_id,
                    decision.decision,
                    decision.reason,
                    json.dumps(decision.alternatives, ensure_ascii=False),
                    json.dumps(decision.rejected_reasons, ensure_ascii=False),
                    decision.source,
                    decision.timestamp,
                ),
            )

    def get_decision(self, decision_id: str) -> Decision | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM decisions WHERE id = ?", (decision_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_decision(row)

    def list_decisions(self, project_id: str) -> list[Decision]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM decisions WHERE project_id = ? ORDER BY timestamp DESC",
                (project_id,),
            ).fetchall()
        return [self._row_to_decision(row) for row in rows]

    def _row_to_decision(self, row: sqlite3.Row) -> Decision:
        return Decision.from_dict({
            "id": row["id"],
            "project_id": row["project_id"],
            "decision": row["decision"],
            "reason": row["reason"] or "",
            "alternatives": json.loads(row["alternatives"] or "[]"),
            "rejected_reasons": json.loads(row["rejected_reasons"] or "{}"),
            "source": row["source"] or "agent",
            "timestamp": row["timestamp"],
        })

    # ------------------------------------------------------------------
    # Artifacts
    # ------------------------------------------------------------------
    def save_artifact(self, artifact: Artifact) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO artifacts (id, project_id, type, title, content, version,
                                       change_reason, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    type=excluded.type,
                    title=excluded.title,
                    content=excluded.content,
                    version=excluded.version,
                    change_reason=excluded.change_reason,
                    updated_at=excluded.updated_at
                """,
                (
                    artifact.id,
                    artifact.project_id,
                    artifact.type,
                    artifact.title,
                    artifact.content,
                    artifact.version,
                    artifact.change_reason,
                    artifact.created_at,
                    artifact.updated_at,
                ),
            )

    def get_artifact(self, artifact_id: str) -> Artifact | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM artifacts WHERE id = ?", (artifact_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_artifact(row)

    def list_artifacts(self, project_id: str) -> list[Artifact]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM artifacts WHERE project_id = ? ORDER BY updated_at DESC",
                (project_id,),
            ).fetchall()
        return [self._row_to_artifact(row) for row in rows]

    def _row_to_artifact(self, row: sqlite3.Row) -> Artifact:
        return Artifact.from_dict({
            "id": row["id"],
            "project_id": row["project_id"],
            "type": row["type"],
            "title": row["title"],
            "content": row["content"] or "",
            "version": row["version"],
            "change_reason": row["change_reason"] or "",
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        })

    # ------------------------------------------------------------------
    # Feedback
    # ------------------------------------------------------------------
    def save_feedback(self, feedback: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO user_feedback (id, user_id, project_id, type, description,
                                           priority, status, metadata, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    user_id=excluded.user_id,
                    project_id=excluded.project_id,
                    type=excluded.type,
                    description=excluded.description,
                    priority=excluded.priority,
                    status=excluded.status,
                    metadata=excluded.metadata,
                    updated_at=excluded.updated_at
                """,
                (
                    feedback["id"],
                    feedback.get("user_id"),
                    feedback.get("project_id"),
                    feedback["type"],
                    feedback["description"],
                    feedback.get("priority", "medium"),
                    feedback.get("status", "open"),
                    json.dumps(feedback.get("metadata") or {}, ensure_ascii=False),
                    feedback.get("created_at", now),
                    feedback.get("updated_at", now),
                ),
            )

    def list_feedback(self, user_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM user_feedback"
        params: tuple[Any, ...] = ()
        if user_id:
            query += " WHERE user_id = ?"
            params = (user_id,)
        query += " ORDER BY created_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_feedback(row) for row in rows]

    def _row_to_feedback(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "user_id": row["user_id"] or "",
            "project_id": row["project_id"] or "",
            "type": row["type"],
            "description": row["description"],
            "priority": row["priority"] or "medium",
            "status": row["status"] or "open",
            "metadata": json.loads(row["metadata"] or "{}"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    # ------------------------------------------------------------------
    # Analytics events
    # ------------------------------------------------------------------
    def save_event(self, event: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO events (user_id, project_id, event_type, payload, session_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event.get("user_id"),
                    event.get("project_id"),
                    event["event_type"],
                    json.dumps(event.get("payload") or {}, ensure_ascii=False),
                    event.get("session_id"),
                    event.get("created_at", now),
                ),
            )

    def list_events(
        self,
        user_id: str | None = None,
        project_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM events"
        conditions: list[str] = []
        params: list[Any] = []
        if user_id:
            conditions.append("user_id = ?")
            params.append(user_id)
        if project_id:
            conditions.append("project_id = ?")
            params.append(project_id)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._row_to_event(row) for row in rows]

    def _row_to_event(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "user_id": row["user_id"] or "",
            "project_id": row["project_id"] or "",
            "event_type": row["event_type"],
            "payload": json.loads(row["payload"] or "{}"),
            "session_id": row["session_id"] or "",
            "created_at": row["created_at"],
        }

    # ------------------------------------------------------------------
    # Error monitoring
    # ------------------------------------------------------------------
    def save_error(self, error: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO error_logs (user_id, project_id, endpoint, method, error_type,
                                        message, stack, payload, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    error.get("user_id"),
                    error.get("project_id"),
                    error.get("endpoint"),
                    error.get("method"),
                    error.get("error_type"),
                    error.get("message"),
                    error.get("stack"),
                    json.dumps(error.get("payload"), ensure_ascii=False) if error.get("payload") is not None else None,
                    error.get("created_at", now),
                ),
            )

    def list_errors(self, limit: int = 100) -> list[dict[str, Any]]:
        query = "SELECT * FROM error_logs ORDER BY created_at DESC LIMIT ?"
        with self._connect() as conn:
            rows = conn.execute(query, (limit,)).fetchall()
        return [self._row_to_error(row) for row in rows]

    def _row_to_error(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "user_id": row["user_id"] or "",
            "project_id": row["project_id"] or "",
            "endpoint": row["endpoint"] or "",
            "method": row["method"] or "",
            "error_type": row["error_type"] or "",
            "message": row["message"] or "",
            "stack": row["stack"] or "",
            "payload": json.loads(row["payload"]) if row["payload"] else None,
            "created_at": row["created_at"],
        }

    # ------------------------------------------------------------------
    # Learning memory
    # ------------------------------------------------------------------
    def save_learning_record(self, record: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO learning_records (id, user_id, source_project_id, memory, memory_type,
                                              source, confidence, verification_status, scope, tags,
                                              created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    memory=excluded.memory,
                    memory_type=excluded.memory_type,
                    source=excluded.source,
                    confidence=excluded.confidence,
                    verification_status=excluded.verification_status,
                    scope=excluded.scope,
                    tags=excluded.tags,
                    updated_at=excluded.updated_at
                """,
                (
                    record["id"],
                    record["user_id"],
                    record.get("source_project_id"),
                    record["memory"],
                    record["memory_type"],
                    record.get("source"),
                    record.get("confidence", "low"),
                    record.get("verification_status", "unverified"),
                    record.get("scope", "private"),
                    json.dumps(record.get("tags") or [], ensure_ascii=False),
                    record.get("created_at", now),
                    record.get("updated_at", now),
                ),
            )

    def list_learning_records(
        self,
        user_id: str,
        source_project_id: str | None = None,
        memory_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM learning_records WHERE user_id = ?"
        params: list[Any] = [user_id]
        if source_project_id:
            query += " AND source_project_id = ?"
            params.append(source_project_id)
        if memory_type:
            query += " AND memory_type = ?"
            params.append(memory_type)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._row_to_learning_record(row) for row in rows]

    def get_learning_record(self, record_id: str, user_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM learning_records WHERE id = ? AND user_id = ?",
                (record_id, user_id),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_learning_record(row)

    def delete_learning_record(self, record_id: str, user_id: str) -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM learning_records WHERE id = ? AND user_id = ?",
                (record_id, user_id),
            )
            return cur.rowcount > 0

    def _row_to_learning_record(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "user_id": row["user_id"] or "",
            "source_project_id": row["source_project_id"] or "",
            "memory": row["memory"],
            "memory_type": row["memory_type"],
            "source": row["source"] or "",
            "confidence": row["confidence"] or "low",
            "verification_status": row["verification_status"] or "unverified",
            "scope": row["scope"] or "private",
            "tags": json.loads(row["tags"] or "[]"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def save_failure_knowledge(self, failure: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO failure_knowledge (id, user_id, source_project_id, problem, cause, solution,
                                               affected_scope, verification, confidence, verification_status,
                                               created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    problem=excluded.problem,
                    cause=excluded.cause,
                    solution=excluded.solution,
                    affected_scope=excluded.affected_scope,
                    verification=excluded.verification,
                    confidence=excluded.confidence,
                    verification_status=excluded.verification_status,
                    updated_at=excluded.updated_at
                """,
                (
                    failure["id"],
                    failure["user_id"],
                    failure.get("source_project_id"),
                    failure["problem"],
                    failure.get("cause"),
                    failure.get("solution"),
                    failure.get("affected_scope"),
                    failure.get("verification"),
                    failure.get("confidence", "medium"),
                    failure.get("verification_status", "unverified"),
                    failure.get("created_at", now),
                    failure.get("updated_at", now),
                ),
            )

    def list_failure_knowledge(
        self,
        user_id: str,
        source_project_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM failure_knowledge WHERE user_id = ?"
        params: list[Any] = [user_id]
        if source_project_id:
            query += " AND source_project_id = ?"
            params.append(source_project_id)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._row_to_failure_knowledge(row) for row in rows]

    def get_failure_knowledge(self, failure_id: str, user_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM failure_knowledge WHERE id = ? AND user_id = ?",
                (failure_id, user_id),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_failure_knowledge(row)

    def delete_failure_knowledge(self, failure_id: str, user_id: str) -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM failure_knowledge WHERE id = ? AND user_id = ?",
                (failure_id, user_id),
            )
            return cur.rowcount > 0

    def _row_to_failure_knowledge(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "user_id": row["user_id"] or "",
            "source_project_id": row["source_project_id"] or "",
            "problem": row["problem"],
            "cause": row["cause"] or "",
            "solution": row["solution"] or "",
            "affected_scope": row["affected_scope"] or "",
            "verification": row["verification"] or "",
            "confidence": row["confidence"] or "medium",
            "verification_status": row["verification_status"] or "unverified",
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def save_success_knowledge(self, success: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO success_knowledge (id, user_id, source_project_id, goal, solution, conditions,
                                               result, confidence, verification_status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    goal=excluded.goal,
                    solution=excluded.solution,
                    conditions=excluded.conditions,
                    result=excluded.result,
                    confidence=excluded.confidence,
                    verification_status=excluded.verification_status,
                    updated_at=excluded.updated_at
                """,
                (
                    success["id"],
                    success["user_id"],
                    success.get("source_project_id"),
                    success.get("goal"),
                    success["solution"],
                    json.dumps(success.get("conditions") or [], ensure_ascii=False),
                    success.get("result"),
                    success.get("confidence", "medium"),
                    success.get("verification_status", "unverified"),
                    success.get("created_at", now),
                    success.get("updated_at", now),
                ),
            )

    def list_success_knowledge(
        self,
        user_id: str,
        source_project_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM success_knowledge WHERE user_id = ?"
        params: list[Any] = [user_id]
        if source_project_id:
            query += " AND source_project_id = ?"
            params.append(source_project_id)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._row_to_success_knowledge(row) for row in rows]

    def get_success_knowledge(self, success_id: str, user_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM success_knowledge WHERE id = ? AND user_id = ?",
                (success_id, user_id),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_success_knowledge(row)

    def delete_success_knowledge(self, success_id: str, user_id: str) -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM success_knowledge WHERE id = ? AND user_id = ?",
                (success_id, user_id),
            )
            return cur.rowcount > 0

    def _row_to_success_knowledge(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "user_id": row["user_id"] or "",
            "source_project_id": row["source_project_id"] or "",
            "goal": row["goal"] or "",
            "solution": row["solution"],
            "conditions": json.loads(row["conditions"] or "[]"),
            "result": row["result"] or "",
            "confidence": row["confidence"] or "medium",
            "verification_status": row["verification_status"] or "unverified",
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def save_suggestion(self, suggestion: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO suggestions (id, user_id, source_project_id, suggestion, reason, evidence,
                                         impact, priority, status, category, related_learning_ids,
                                         created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    suggestion=excluded.suggestion,
                    reason=excluded.reason,
                    evidence=excluded.evidence,
                    impact=excluded.impact,
                    priority=excluded.priority,
                    status=excluded.status,
                    category=excluded.category,
                    related_learning_ids=excluded.related_learning_ids,
                    updated_at=excluded.updated_at
                """,
                (
                    suggestion["id"],
                    suggestion["user_id"],
                    suggestion["source_project_id"],
                    suggestion["suggestion"],
                    suggestion.get("reason"),
                    json.dumps(suggestion.get("evidence") or [], ensure_ascii=False),
                    suggestion.get("impact"),
                    suggestion.get("priority", "medium"),
                    suggestion.get("status", "new"),
                    suggestion.get("category"),
                    json.dumps(suggestion.get("related_learning_ids") or [], ensure_ascii=False),
                    suggestion.get("created_at", now),
                    suggestion.get("updated_at", now),
                ),
            )

    def list_suggestions(
        self,
        user_id: str,
        source_project_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM suggestions WHERE user_id = ?"
        params: list[Any] = [user_id]
        if source_project_id:
            query += " AND source_project_id = ?"
            params.append(source_project_id)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._row_to_suggestion(row) for row in rows]

    def get_suggestion(self, suggestion_id: str, user_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM suggestions WHERE id = ? AND user_id = ?",
                (suggestion_id, user_id),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_suggestion(row)

    def update_suggestion_status(self, suggestion_id: str, user_id: str, status: str) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "UPDATE suggestions SET status = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                (status, now, suggestion_id, user_id),
            )
            return cur.rowcount > 0

    def delete_suggestion(self, suggestion_id: str, user_id: str) -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM suggestions WHERE id = ? AND user_id = ?",
                (suggestion_id, user_id),
            )
            return cur.rowcount > 0

    def _row_to_suggestion(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "user_id": row["user_id"] or "",
            "source_project_id": row["source_project_id"] or "",
            "suggestion": row["suggestion"],
            "reason": row["reason"] or "",
            "evidence": json.loads(row["evidence"] or "[]"),
            "impact": row["impact"] or "",
            "priority": row["priority"] or "medium",
            "status": row["status"] or "new",
            "category": row["category"] or "",
            "related_learning_ids": json.loads(row["related_learning_ids"] or "[]"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    # ------------------------------------------------------------------
    # Chat messages
    # ------------------------------------------------------------------
    def save_chat_message(self, message: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO chat_messages (id, user_id, project_id, role, content, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    role=excluded.role,
                    content=excluded.content,
                    metadata=excluded.metadata
                """,
                (
                    message["id"],
                    message["user_id"],
                    message["project_id"],
                    message["role"],
                    message["content"],
                    json.dumps(message.get("metadata") or {}, ensure_ascii=False),
                    message.get("created_at", now),
                ),
            )

    def list_chat_messages(
        self,
        project_id: str,
        user_id: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM chat_messages WHERE project_id = ?"
        params: list[Any] = [project_id]
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        query += " ORDER BY created_at ASC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_chat_message(row) for row in rows]

    def delete_chat_messages(self, project_id: str, user_id: str) -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM chat_messages WHERE project_id = ? AND user_id = ?",
                (project_id, user_id),
            )
            return cur.rowcount > 0

    def _row_to_chat_message(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "user_id": row["user_id"] or "",
            "project_id": row["project_id"] or "",
            "role": row["role"] or "",
            "content": row["content"] or "",
            "metadata": json.loads(row["metadata"] or "{}"),
            "created_at": row["created_at"],
        }

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------
    def close(self) -> None:
        pass
