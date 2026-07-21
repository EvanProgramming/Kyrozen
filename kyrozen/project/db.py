"""SQLite persistence for the Kyrozen Project Workspace."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from .project import Artifact, Decision, Project


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    goal TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    current_stage TEXT NOT NULL DEFAULT 'problem_discovery',
    next_steps TEXT,
    risks TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
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
                INSERT INTO projects (id, name, description, goal, status, current_stage,
                                      next_steps, risks, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    description=excluded.description,
                    goal=excluded.goal,
                    status=excluded.status,
                    current_stage=excluded.current_stage,
                    next_steps=excluded.next_steps,
                    risks=excluded.risks,
                    updated_at=excluded.updated_at
                """,
                (
                    project.id,
                    project.name,
                    project.description,
                    project.goal,
                    project.status,
                    project.current_stage,
                    project.next_steps,
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

    def list_projects(self) -> list[Project]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM projects ORDER BY updated_at DESC"
            ).fetchall()
        return [self._row_to_project(row) for row in rows]

    def delete_project(self, project_id: str) -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            return cur.rowcount > 0

    def _row_to_project(self, row: sqlite3.Row) -> Project:
        return Project.from_dict({
            "id": row["id"],
            "name": row["name"],
            "description": row["description"] or "",
            "goal": row["goal"] or "",
            "status": row["status"],
            "current_stage": row["current_stage"],
            "next_steps": row["next_steps"] or "",
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
    # Utility
    # ------------------------------------------------------------------
    def close(self) -> None:
        pass
