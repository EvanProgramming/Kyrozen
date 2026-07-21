"""Task management system for Kyrozen Core."""

from __future__ import annotations

import json
import os
import threading
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any


TASK_STATUSES = {"pending", "running", "waiting_confirmation", "completed", "failed", "cancelled"}


@dataclass
class TaskStep:
    """A single step inside a task."""

    description: str
    status: str = "pending"
    result: Any = None
    error: str = ""
    started_at: str = ""
    completed_at: str = ""

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
    ) -> None:
        self.id = task_id or f"task_{uuid.uuid4().hex[:8]}"
        self.title = title
        self.description = description
        self.status = status
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.updated_at = self.created_at
        self.steps: list[TaskStep] = []
        self.result: Any = None
        self.errors: list[str] = []

    def update_status(self, status: str) -> None:
        if status not in TASK_STATUSES:
            raise ValueError(f"Invalid status '{status}'. Valid: {TASK_STATUSES}")
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
    """Manage tasks in memory with optional JSON persistence."""

    def __init__(self, store_path: str = "./kyrozen_tasks.json") -> None:
        self.store_path = store_path
        self._tasks: dict[str, Task] = {}
        self._lock = threading.Lock()
        self._load()

    def create(self, title: str, description: str = "") -> Task:
        task = Task(title=title, description=description)
        with self._lock:
            self._tasks[task.id] = task
            self._save()
        return task

    def get(self, task_id: str) -> Task | None:
        with self._lock:
            return self._tasks.get(task_id)

    def update(self, task: Task) -> None:
        with self._lock:
            self._tasks[task.id] = task
            self._save()

    def list_tasks(self) -> list[Task]:
        with self._lock:
            return list(self._tasks.values())

    def _save(self) -> None:
        try:
            data = {tid: task.to_dict() for tid, task in self._tasks.items()}
            with open(self.store_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load(self) -> None:
        if not os.path.exists(self.store_path):
            return
        try:
            with open(self.store_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for tid, task_data in data.items():
                self._tasks[tid] = Task.from_dict(task_data)
        except Exception:
            pass
