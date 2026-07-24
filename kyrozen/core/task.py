"""Task management system for Kyrozen Core."""

from __future__ import annotations

import json
import os
import threading
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any

from kyrozen.logs import get_logger


TASK_STATUSES = {"pending", "running", "waiting_confirmation", "completed", "failed", "cancelled"}

# Valid status transitions. Terminal states cannot change unless forced.
VALID_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"running", "completed", "failed", "cancelled"},
    "running": {"waiting_confirmation", "completed", "failed", "cancelled"},
    "waiting_confirmation": {"running", "completed", "failed", "cancelled"},
    "completed": set(),
    "failed": set(),
    "cancelled": set(),
}


@dataclass
class TaskStep:
    """A single step inside a task."""

    description: str
    status: str = "pending"
    result: Any = None
    error: str = ""
    started_at: str = ""
    completed_at: str = ""
    metadata: dict[str, Any] = None

    def __post_init__(self) -> None:
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Task:
    """A long-running task with status, steps, results, and errors."""

    def __init__(
        self,
        title: str,
        description: str = "",
        task_id: str | None = None,
        status: str = "pending",
        project_id: str | None = None,
        mode: str | None = None,
        requires_local_client: bool = False,
        assigned_client_id: str | None = None,
    ) -> None:
        self.id = task_id or f"task_{uuid.uuid4().hex[:8]}"
        self.title = title
        self.description = description
        self.status = status
        self.project_id = project_id
        self.mode = mode
        self.requires_local_client = requires_local_client
        self.assigned_client_id = assigned_client_id
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.updated_at = self.created_at
        self.steps: list[TaskStep] = []
        self.result: Any = None
        self.errors: list[str] = []

    def update_status(self, status: str, force: bool = False) -> None:
        if status not in TASK_STATUSES:
            raise ValueError(f"Invalid status '{status}'. Valid: {TASK_STATUSES}")
        if not force and status not in VALID_STATUS_TRANSITIONS.get(self.status, set()):
            raise ValueError(f"Invalid status transition from '{self.status}' to '{status}'")
        self.status = status
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def add_step(self, description: str) -> TaskStep:
        step = TaskStep(description=description)
        self.steps.append(step)
        self.updated_at = datetime.now(timezone.utc).isoformat()
        return step

    def fail(self, error: str) -> None:
        self.errors.append(error)
        self.update_status("failed")

    def complete(self, result: Any = None) -> None:
        self.result = result
        self.update_status("completed")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "project_id": self.project_id,
            "mode": self.mode,
            "requires_local_client": self.requires_local_client,
            "assigned_client_id": self.assigned_client_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "steps": [s.to_dict() for s in self.steps],
            "result": self.result,
            "errors": self.errors,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        task = cls(
            title=data.get("title", ""),
            description=data.get("description", ""),
            task_id=data.get("id"),
            status=data.get("status", "pending"),
            project_id=data.get("project_id"),
            mode=data.get("mode"),
            requires_local_client=data.get("requires_local_client", False),
            assigned_client_id=data.get("assigned_client_id"),
        )
        task.created_at = data.get("created_at", task.created_at)
        task.updated_at = data.get("updated_at", task.updated_at)
        task.result = data.get("result")
        task.errors = data.get("errors", [])
        for step_data in data.get("steps", []):
            step = TaskStep(**step_data)
            task.steps.append(step)
        return task


class TaskManager:
    """Manage tasks with optional JSON file or SQLite persistence."""

    def __init__(
        self,
        store_path: str = "./kyrozen_tasks.json",
        db: Any | None = None,
        logger: Any | None = None,
    ) -> None:
        self.store_path = store_path
        self.db = db
        self._tasks: dict[str, Task] = {}
        self._lock = threading.Lock()
        self._logger = logger or get_logger("INFO")
        if db is not None:
            self._load_from_db()
        else:
            self._load()

    def create(
        self,
        title: str,
        description: str = "",
        project_id: str | None = None,
        mode: str | None = None,
        requires_local_client: bool = False,
        assigned_client_id: str | None = None,
    ) -> Task:
        task = Task(
            title=title,
            description=description,
            project_id=project_id,
            mode=mode,
            requires_local_client=requires_local_client,
            assigned_client_id=assigned_client_id,
        )
        with self._lock:
            self._tasks[task.id] = task
            self._save(task)
        return task

    def get(self, task_id: str) -> Task | None:
        with self._lock:
            task = self._tasks.get(task_id)
        if task is None and self.db is not None:
            task = self.db.get_task(task_id)
            if task:
                with self._lock:
                    self._tasks[task.id] = task
        return task

    def update(self, task: Task) -> None:
        with self._lock:
            self._tasks[task.id] = task
            self._save(task)

    def list_tasks(self, project_id: str | None = None) -> list[Task]:
        if self.db is not None:
            return self.db.list_tasks(project_id=project_id)
        with self._lock:
            tasks = list(self._tasks.values())
        if project_id:
            tasks = [t for t in tasks if t.project_id == project_id]
        return tasks

    def _save(self, task: Task) -> None:
        if self.db is not None:
            try:
                self.db.save_task(task)
            except Exception as exc:
                self._logger.error(f"Failed to save task {task.id} to database: {exc}")
                raise RuntimeError(f"Failed to persist task {task.id}") from exc
            return
        try:
            data = {tid: t.to_dict() for tid, t in self._tasks.items()}
            with open(self.store_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            self._logger.error(f"Failed to save task {task.id} to {self.store_path}: {exc}")
            raise RuntimeError(f"Failed to persist task {task.id}") from exc

    def _load(self) -> None:
        if not os.path.exists(self.store_path):
            return
        try:
            with open(self.store_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for tid, task_data in data.items():
                self._tasks[tid] = Task.from_dict(task_data)
        except Exception as exc:
            self._logger.error(f"Failed to load tasks from {self.store_path}: {exc}")

    def _load_from_db(self) -> None:
        if self.db is None:
            return
        try:
            for task in self.db.list_tasks():
                self._tasks[task.id] = task
        except Exception as exc:
            self._logger.error(f"Failed to load tasks from database: {exc}")
