"""Self-hosted PostgreSQL persistence adapter for Kyrozen."""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool

from .project import Artifact, Decision, Project


logger = logging.getLogger(__name__)


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
    mode TEXT,
    requires_local_client INTEGER NOT NULL DEFAULT 0,
    assigned_client_id TEXT,
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
    id SERIAL PRIMARY KEY,
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
    id SERIAL PRIMARY KEY,
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

CREATE TABLE IF NOT EXISTS desktop_clients (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    device_name TEXT NOT NULL DEFAULT 'Unknown Device',
    client_version TEXT,
    platform TEXT,
    last_active_at TEXT NOT NULL,
    online INTEGER NOT NULL DEFAULT 1,
    current_project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_desktop_clients_user ON desktop_clients(user_id);
CREATE INDEX IF NOT EXISTS idx_desktop_clients_online ON desktop_clients(user_id, online, last_active_at);
"""


def _adapt_sql(sql: str) -> str:
    """Convert SQLite-style SQL to PostgreSQL-compatible syntax."""
    # psycopg2 uses %s placeholders; literal % must be escaped as %%
    sql = sql.replace("?", "%s")
    # INTEGER PRIMARY KEY AUTOINCREMENT -> SERIAL PRIMARY KEY
    sql = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
    return sql


class PostgresDatabase:
    """Thread-safe PostgreSQL database for projects, tasks, decisions, and artifacts."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self._lock = threading.Lock()
        self._pool: ThreadedConnectionPool | None = None
        self._ensure_connection()
        self._init_schema()

    def _ensure_connection(self) -> None:
        try:
            self._pool = ThreadedConnectionPool(
                minconn=1,
                maxconn=10,
                dsn=self.dsn,
            )
        except psycopg2.Error as exc:
            logger.error("Failed to connect to PostgreSQL: %s", exc)
            raise

    def _connect(self):
        if self._pool is None:
            self._ensure_connection()
        return self._pool.getconn()

    def _putconn(self, conn) -> None:
        if self._pool is not None:
            self._pool.putconn(conn)

    def _init_schema(self) -> None:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(_adapt_sql(SCHEMA_SQL))
                self._migrate_tasks_table(cur)
            conn.commit()
        finally:
            self._putconn(conn)

    def _migrate_tasks_table(self, cur) -> None:
        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'tasks'
            """
        )
        columns = {row[0] for row in cur.fetchall()}
        if "mode" not in columns:
            cur.execute("ALTER TABLE tasks ADD COLUMN mode TEXT")
        if "requires_local_client" not in columns:
            cur.execute("ALTER TABLE tasks ADD COLUMN requires_local_client INTEGER NOT NULL DEFAULT 0")
        if "assigned_client_id" not in columns:
            cur.execute("ALTER TABLE tasks ADD COLUMN assigned_client_id TEXT")

    def _execute(
        self,
        sql: str,
        params: tuple[Any, ...] | list[Any] = (),
        fetch: str | None = None,
    ) -> Any:
        sql = _adapt_sql(sql)
        conn = self._connect()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, params)
                result = None
                if fetch == "one":
                    result = cur.fetchone()
                elif fetch == "all":
                    result = cur.fetchall()
                elif fetch == "rowcount":
                    result = cur.rowcount
            conn.commit()
            return result
        finally:
            self._putconn(conn)

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------
    def save_project(self, project: Project) -> None:
        with self._lock:
            self._execute(
                """
                INSERT INTO projects (id, user_id, name, description, goal, status, current_stage,
                                      next_steps, blocked_reason, progress, risks, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    user_id=EXCLUDED.user_id,
                    name=EXCLUDED.name,
                    description=EXCLUDED.description,
                    goal=EXCLUDED.goal,
                    status=EXCLUDED.status,
                    current_stage=EXCLUDED.current_stage,
                    next_steps=EXCLUDED.next_steps,
                    blocked_reason=EXCLUDED.blocked_reason,
                    progress=EXCLUDED.progress,
                    risks=EXCLUDED.risks,
                    updated_at=EXCLUDED.updated_at
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
        row = self._execute(
            "SELECT * FROM projects WHERE id = %s",
            (project_id,),
            fetch="one",
        )
        if row is None:
            return None
        return self._row_to_project(row)

    def list_projects(self, user_id: str | None = None) -> list[Project]:
        query = "SELECT * FROM projects"
        params: tuple[Any, ...] = ()
        if user_id:
            query += " WHERE user_id = %s"
            params = (user_id,)
        query += " ORDER BY updated_at DESC"
        rows = self._execute(query, params, fetch="all") or []
        return [self._row_to_project(row) for row in rows]

    def delete_project(self, project_id: str) -> bool:
        result = self._execute(
            "DELETE FROM projects WHERE id = %s",
            (project_id,),
            fetch="rowcount",
        )
        return bool(result and result > 0)

    def _row_to_project(self, row: dict[str, Any]) -> Project:
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
        with self._lock:
            self._execute(
                """
                INSERT INTO tasks (id, project_id, title, description, status, mode,
                                   requires_local_client, assigned_client_id, steps,
                                   result, errors, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    project_id=EXCLUDED.project_id,
                    title=EXCLUDED.title,
                    description=EXCLUDED.description,
                    status=EXCLUDED.status,
                    mode=EXCLUDED.mode,
                    requires_local_client=EXCLUDED.requires_local_client,
                    assigned_client_id=EXCLUDED.assigned_client_id,
                    steps=EXCLUDED.steps,
                    result=EXCLUDED.result,
                    errors=EXCLUDED.errors,
                    updated_at=EXCLUDED.updated_at
                """,
                (
                    task.id,
                    getattr(task, "project_id", None),
                    task.title,
                    task.description,
                    task.status,
                    getattr(task, "mode", None),
                    1 if getattr(task, "requires_local_client", False) else 0,
                    getattr(task, "assigned_client_id", None),
                    json.dumps([s.to_dict() for s in task.steps], ensure_ascii=False),
                    json.dumps(task.result, ensure_ascii=False) if task.result is not None else None,
                    json.dumps(task.errors, ensure_ascii=False),
                    task.created_at,
                    task.updated_at,
                ),
            )

    def get_task(self, task_id: str) -> Any | None:
        from kyrozen.core.task import Task
        row = self._execute(
            "SELECT * FROM tasks WHERE id = %s",
            (task_id,),
            fetch="one",
        )
        if row is None:
            return None
        return self._row_to_task(row, Task)

    def list_tasks(self, project_id: str | None = None) -> list[Any]:
        from kyrozen.core.task import Task
        query = "SELECT * FROM tasks"
        params: tuple[Any, ...] = ()
        if project_id:
            query += " WHERE project_id = %s"
            params = (project_id,)
        query += " ORDER BY updated_at DESC"
        rows = self._execute(query, params, fetch="all") or []
        return [self._row_to_task(row, Task) for row in rows]

    def _row_to_task(self, row: dict[str, Any], TaskCls: type) -> Any:
        from kyrozen.core.task import TaskStep
        task = TaskCls(
            title=row["title"],
            description=row["description"] or "",
            task_id=row["id"],
            status=row["status"],
            project_id=row["project_id"],
            mode=row["mode"],
            requires_local_client=bool(row["requires_local_client"]),
            assigned_client_id=row["assigned_client_id"],
        )
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
        self._execute(
            """
            INSERT INTO decisions (id, project_id, decision, reason, alternatives,
                                   rejected_reasons, source, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                decision=EXCLUDED.decision,
                reason=EXCLUDED.reason,
                alternatives=EXCLUDED.alternatives,
                rejected_reasons=EXCLUDED.rejected_reasons,
                source=EXCLUDED.source,
                timestamp=EXCLUDED.timestamp
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
        row = self._execute(
            "SELECT * FROM decisions WHERE id = %s",
            (decision_id,),
            fetch="one",
        )
        if row is None:
            return None
        return self._row_to_decision(row)

    def list_decisions(self, project_id: str) -> list[Decision]:
        rows = self._execute(
            "SELECT * FROM decisions WHERE project_id = %s ORDER BY timestamp DESC",
            (project_id,),
            fetch="all",
        ) or []
        return [self._row_to_decision(row) for row in rows]

    def _row_to_decision(self, row: dict[str, Any]) -> Decision:
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
        self._execute(
            """
            INSERT INTO artifacts (id, project_id, type, title, content, version,
                                   change_reason, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                type=EXCLUDED.type,
                title=EXCLUDED.title,
                content=EXCLUDED.content,
                version=EXCLUDED.version,
                change_reason=EXCLUDED.change_reason,
                updated_at=EXCLUDED.updated_at
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
        row = self._execute(
            "SELECT * FROM artifacts WHERE id = %s",
            (artifact_id,),
            fetch="one",
        )
        if row is None:
            return None
        return self._row_to_artifact(row)

    def list_artifacts(self, project_id: str) -> list[Artifact]:
        rows = self._execute(
            "SELECT * FROM artifacts WHERE project_id = %s ORDER BY updated_at DESC",
            (project_id,),
            fetch="all",
        ) or []
        return [self._row_to_artifact(row) for row in rows]

    def _row_to_artifact(self, row: dict[str, Any]) -> Artifact:
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
        self._execute(
            """
            INSERT INTO user_feedback (id, user_id, project_id, type, description,
                                       priority, status, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                user_id=EXCLUDED.user_id,
                project_id=EXCLUDED.project_id,
                type=EXCLUDED.type,
                description=EXCLUDED.description,
                priority=EXCLUDED.priority,
                status=EXCLUDED.status,
                metadata=EXCLUDED.metadata,
                updated_at=EXCLUDED.updated_at
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
            query += " WHERE user_id = %s"
            params = (user_id,)
        query += " ORDER BY created_at DESC"
        rows = self._execute(query, params, fetch="all") or []
        return [self._row_to_feedback(row) for row in rows]

    def _row_to_feedback(self, row: dict[str, Any]) -> dict[str, Any]:
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
        self._execute(
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
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM events"
        conditions: list[str] = []
        params: list[Any] = []
        if user_id:
            conditions.append("user_id = %s")
            params.append(user_id)
        if project_id:
            conditions.append("project_id = %s")
            params.append(project_id)
        if event_type:
            conditions.append("event_type = %s")
            params.append(event_type)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)
        rows = self._execute(query, params, fetch="all") or []
        return [self._row_to_event(row) for row in rows]

    def _row_to_event(self, row: dict[str, Any]) -> dict[str, Any]:
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
        self._execute(
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
        rows = self._execute(
            "SELECT * FROM error_logs ORDER BY created_at DESC LIMIT %s",
            (limit,),
            fetch="all",
        ) or []
        return [self._row_to_error(row) for row in rows]

    def _row_to_error(self, row: dict[str, Any]) -> dict[str, Any]:
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
        self._execute(
            """
            INSERT INTO learning_records (id, user_id, source_project_id, memory, memory_type,
                                          source, confidence, verification_status, scope, tags,
                                          created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                memory=EXCLUDED.memory,
                memory_type=EXCLUDED.memory_type,
                source=EXCLUDED.source,
                confidence=EXCLUDED.confidence,
                verification_status=EXCLUDED.verification_status,
                scope=EXCLUDED.scope,
                tags=EXCLUDED.tags,
                updated_at=EXCLUDED.updated_at
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
        query = "SELECT * FROM learning_records WHERE user_id = %s"
        params: list[Any] = [user_id]
        if source_project_id:
            query += " AND source_project_id = %s"
            params.append(source_project_id)
        if memory_type:
            query += " AND memory_type = %s"
            params.append(memory_type)
        query += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)
        rows = self._execute(query, params, fetch="all") or []
        return [self._row_to_learning_record(row) for row in rows]

    def get_learning_record(self, record_id: str, user_id: str) -> dict[str, Any] | None:
        row = self._execute(
            "SELECT * FROM learning_records WHERE id = %s AND user_id = %s",
            (record_id, user_id),
            fetch="one",
        )
        if row is None:
            return None
        return self._row_to_learning_record(row)

    def delete_learning_record(self, record_id: str, user_id: str) -> bool:
        result = self._execute(
            "DELETE FROM learning_records WHERE id = %s AND user_id = %s",
            (record_id, user_id),
            fetch="rowcount",
        )
        return bool(result and result > 0)

    def _row_to_learning_record(self, row: dict[str, Any]) -> dict[str, Any]:
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
        self._execute(
            """
            INSERT INTO failure_knowledge (id, user_id, source_project_id, problem, cause, solution,
                                           affected_scope, verification, confidence, verification_status,
                                           created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                problem=EXCLUDED.problem,
                cause=EXCLUDED.cause,
                solution=EXCLUDED.solution,
                affected_scope=EXCLUDED.affected_scope,
                verification=EXCLUDED.verification,
                confidence=EXCLUDED.confidence,
                verification_status=EXCLUDED.verification_status,
                updated_at=EXCLUDED.updated_at
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
        query = "SELECT * FROM failure_knowledge WHERE user_id = %s"
        params: list[Any] = [user_id]
        if source_project_id:
            query += " AND source_project_id = %s"
            params.append(source_project_id)
        query += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)
        rows = self._execute(query, params, fetch="all") or []
        return [self._row_to_failure_knowledge(row) for row in rows]

    def get_failure_knowledge(self, failure_id: str, user_id: str) -> dict[str, Any] | None:
        row = self._execute(
            "SELECT * FROM failure_knowledge WHERE id = %s AND user_id = %s",
            (failure_id, user_id),
            fetch="one",
        )
        if row is None:
            return None
        return self._row_to_failure_knowledge(row)

    def delete_failure_knowledge(self, failure_id: str, user_id: str) -> bool:
        result = self._execute(
            "DELETE FROM failure_knowledge WHERE id = %s AND user_id = %s",
            (failure_id, user_id),
            fetch="rowcount",
        )
        return bool(result and result > 0)

    def _row_to_failure_knowledge(self, row: dict[str, Any]) -> dict[str, Any]:
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
        self._execute(
            """
            INSERT INTO success_knowledge (id, user_id, source_project_id, goal, solution, conditions,
                                           result, confidence, verification_status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                goal=EXCLUDED.goal,
                solution=EXCLUDED.solution,
                conditions=EXCLUDED.conditions,
                result=EXCLUDED.result,
                confidence=EXCLUDED.confidence,
                verification_status=EXCLUDED.verification_status,
                updated_at=EXCLUDED.updated_at
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
        query = "SELECT * FROM success_knowledge WHERE user_id = %s"
        params: list[Any] = [user_id]
        if source_project_id:
            query += " AND source_project_id = %s"
            params.append(source_project_id)
        query += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)
        rows = self._execute(query, params, fetch="all") or []
        return [self._row_to_success_knowledge(row) for row in rows]

    def get_success_knowledge(self, success_id: str, user_id: str) -> dict[str, Any] | None:
        row = self._execute(
            "SELECT * FROM success_knowledge WHERE id = %s AND user_id = %s",
            (success_id, user_id),
            fetch="one",
        )
        if row is None:
            return None
        return self._row_to_success_knowledge(row)

    def delete_success_knowledge(self, success_id: str, user_id: str) -> bool:
        result = self._execute(
            "DELETE FROM success_knowledge WHERE id = %s AND user_id = %s",
            (success_id, user_id),
            fetch="rowcount",
        )
        return bool(result and result > 0)

    def _row_to_success_knowledge(self, row: dict[str, Any]) -> dict[str, Any]:
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
        self._execute(
            """
            INSERT INTO suggestions (id, user_id, source_project_id, suggestion, reason, evidence,
                                     impact, priority, status, category, related_learning_ids,
                                     created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                suggestion=EXCLUDED.suggestion,
                reason=EXCLUDED.reason,
                evidence=EXCLUDED.evidence,
                impact=EXCLUDED.impact,
                priority=EXCLUDED.priority,
                status=EXCLUDED.status,
                category=EXCLUDED.category,
                related_learning_ids=EXCLUDED.related_learning_ids,
                updated_at=EXCLUDED.updated_at
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
        query = "SELECT * FROM suggestions WHERE user_id = %s"
        params: list[Any] = [user_id]
        if source_project_id:
            query += " AND source_project_id = %s"
            params.append(source_project_id)
        if status:
            query += " AND status = %s"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)
        rows = self._execute(query, params, fetch="all") or []
        return [self._row_to_suggestion(row) for row in rows]

    def get_suggestion(self, suggestion_id: str, user_id: str) -> dict[str, Any] | None:
        row = self._execute(
            "SELECT * FROM suggestions WHERE id = %s AND user_id = %s",
            (suggestion_id, user_id),
            fetch="one",
        )
        if row is None:
            return None
        return self._row_to_suggestion(row)

    def update_suggestion_status(self, suggestion_id: str, user_id: str, status: str) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        result = self._execute(
            "UPDATE suggestions SET status = %s, updated_at = %s WHERE id = %s AND user_id = %s",
            (status, now, suggestion_id, user_id),
            fetch="rowcount",
        )
        return bool(result and result > 0)

    def delete_suggestion(self, suggestion_id: str, user_id: str) -> bool:
        result = self._execute(
            "DELETE FROM suggestions WHERE id = %s AND user_id = %s",
            (suggestion_id, user_id),
            fetch="rowcount",
        )
        return bool(result and result > 0)

    def _row_to_suggestion(self, row: dict[str, Any]) -> dict[str, Any]:
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
        self._execute(
            """
            INSERT INTO chat_messages (id, user_id, project_id, role, content, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                role=EXCLUDED.role,
                content=EXCLUDED.content,
                metadata=EXCLUDED.metadata
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
        query = "SELECT * FROM chat_messages WHERE project_id = %s"
        params: list[Any] = [project_id]
        if user_id:
            query += " AND user_id = %s"
            params.append(user_id)
        query += " ORDER BY created_at ASC LIMIT %s"
        params.append(limit)
        rows = self._execute(query, params, fetch="all") or []
        return [self._row_to_chat_message(row) for row in rows]

    def delete_chat_messages(self, project_id: str, user_id: str) -> bool:
        result = self._execute(
            "DELETE FROM chat_messages WHERE project_id = %s AND user_id = %s",
            (project_id, user_id),
            fetch="rowcount",
        )
        return bool(result and result > 0)

    def _row_to_chat_message(self, row: dict[str, Any]) -> dict[str, Any]:
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
    # Desktop clients
    # ------------------------------------------------------------------
    def save_desktop_client(self, client: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._execute(
            """
            INSERT INTO desktop_clients (id, user_id, device_name, client_version, platform,
                                         last_active_at, online, current_project_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                device_name=EXCLUDED.device_name,
                client_version=EXCLUDED.client_version,
                platform=EXCLUDED.platform,
                last_active_at=EXCLUDED.last_active_at,
                online=EXCLUDED.online,
                current_project_id=EXCLUDED.current_project_id,
                updated_at=EXCLUDED.updated_at
            """,
            (
                client["id"],
                client["user_id"],
                client.get("device_name", "Unknown Device"),
                client.get("client_version"),
                client.get("platform"),
                client.get("last_active_at", now),
                1 if client.get("online", True) else 0,
                client.get("current_project_id"),
                client.get("created_at", now),
                client.get("updated_at", now),
            ),
        )

    def get_desktop_client(self, client_id: str) -> dict[str, Any] | None:
        row = self._execute(
            "SELECT * FROM desktop_clients WHERE id = %s",
            (client_id,),
            fetch="one",
        )
        if row is None:
            return None
        return self._row_to_desktop_client(row)

    def list_desktop_clients(
        self,
        user_id: str,
        online_only: bool = False,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM desktop_clients WHERE user_id = %s"
        params: list[Any] = [user_id]
        if online_only:
            query += " AND online = 1"
        query += " ORDER BY last_active_at DESC LIMIT %s"
        params.append(limit)
        rows = self._execute(query, params, fetch="all") or []
        return [self._row_to_desktop_client(row) for row in rows]

    def delete_desktop_client(self, client_id: str, user_id: str) -> bool:
        result = self._execute(
            "DELETE FROM desktop_clients WHERE id = %s AND user_id = %s",
            (client_id, user_id),
            fetch="rowcount",
        )
        return bool(result and result > 0)

    def _row_to_desktop_client(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "user_id": row["user_id"] or "",
            "device_name": row["device_name"] or "Unknown Device",
            "client_version": row["client_version"] or "",
            "platform": row["platform"] or "",
            "last_active_at": row["last_active_at"],
            "online": bool(row["online"]),
            "current_project_id": row["current_project_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------
    def close(self) -> None:
        if self._pool is not None:
            self._pool.closeall()
            self._pool = None
